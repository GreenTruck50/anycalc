"""Reusable JSON-over-HTTP helpers with a bounded in-memory response cache."""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from http.client import HTTPException
import json
import time
from threading import RLock
from typing import Any, Callable
from urllib.request import Request, urlopen


_DEFAULT_CACHE_TTL_SECONDS = 60 * 60
_DEFAULT_MAX_CACHE_ENTRIES = 128
_TIMEOUT_SECONDS = 10
_CACHE_MISS = object()


class NetworkError(RuntimeError):
    """Raised when an HTTP request fails or does not return valid JSON."""


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    payload: Any


class JsonHttpClient:
    """Fetch JSON with optional TTL caching shared by all API clients."""

    def __init__(
        self,
        fetch_json: Callable[[str], Any] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_cache_entries: int = _DEFAULT_MAX_CACHE_ENTRIES,
    ) -> None:
        if max_cache_entries < 1:
            raise ValueError("max_cache_entries must be positive")
        self._fetch_json = fetch_json if fetch_json is not None else _download_json
        self._clock = clock
        self._max_cache_entries = max_cache_entries
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._cache_lock = RLock()

    def get_json(
        self,
        url: str,
        *,
        cache_ttl: float = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> Any:
        """Return JSON from a URL, optionally reusing a cached response."""

        if cache_ttl < 0:
            raise ValueError("cache_ttl cannot be negative")

        if cache_ttl:
            cached = self._get_cached(url)
            if cached is not _CACHE_MISS:
                return cached

        payload = self._fetch_json(url)
        if cache_ttl:
            with self._cache_lock:
                self._cache[url] = _CacheEntry(
                    expires_at=self._clock() + cache_ttl,
                    payload=deepcopy(payload),
                )
                self._cache.move_to_end(url)
                self._evict_expired_and_excess()
        return deepcopy(payload)

    def clear_cache(self) -> None:
        """Remove cached responses from this client."""

        with self._cache_lock:
            self._cache.clear()

    def _get_cached(self, url: str) -> Any:
        with self._cache_lock:
            entry = self._cache.get(url)
            if entry is None:
                return _CACHE_MISS
            if entry.expires_at <= self._clock():
                del self._cache[url]
                return _CACHE_MISS
            self._cache.move_to_end(url)
            return deepcopy(entry.payload)

    def _evict_expired_and_excess(self) -> None:
        now = self._clock()
        for url, entry in tuple(self._cache.items()):
            if entry.expires_at <= now:
                del self._cache[url]
        while len(self._cache) > self._max_cache_entries:
            self._cache.popitem(last=False)


def _download_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "anycalc"})
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
        return json.loads(body, parse_float=Decimal)
    except (
        HTTPException,
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise NetworkError(f"Could not fetch JSON from {url}: {error}") from error


_default_client = JsonHttpClient()


def get_json(
    url: str,
    *,
    cache_ttl: float = _DEFAULT_CACHE_TTL_SECONDS,
) -> Any:
    """Fetch JSON using the process-wide cache."""

    return _default_client.get_json(url, cache_ttl=cache_ttl)


def clear_cache() -> None:
    """Clear the process-wide JSON response cache."""

    _default_client.clear_cache()
