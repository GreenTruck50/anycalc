from decimal import Decimal

import pytest

import networking
from networking import JsonHttpClient, NetworkError


def test_json_client_caches_responses_and_returns_independent_values() -> None:
    calls: list[str] = []

    def fetch_json(url: str) -> dict:
        calls.append(url)
        return {"rates": {"eur": Decimal("0.9")}}

    client = JsonHttpClient(fetch_json)

    first = client.get_json("https://example.test/rates")
    first["rates"]["eur"] = Decimal("99")
    second = client.get_json("https://example.test/rates")

    assert second == {"rates": {"eur": Decimal("0.9")}}
    assert calls == ["https://example.test/rates"]


def test_json_client_expires_entries_after_ttl() -> None:
    now = [0.0]
    calls: list[str] = []

    def fetch_json(url: str) -> dict:
        calls.append(url)
        return {"request": len(calls)}

    client = JsonHttpClient(fetch_json, clock=lambda: now[0])

    assert client.get_json("https://example.test/data", cache_ttl=10) == {
        "request": 1
    }
    now[0] = 9.9
    assert client.get_json("https://example.test/data", cache_ttl=10) == {
        "request": 1
    }
    now[0] = 10.0
    assert client.get_json("https://example.test/data", cache_ttl=10) == {
        "request": 2
    }
    assert len(calls) == 2


def test_json_client_can_bypass_cache() -> None:
    calls: list[str] = []
    client = JsonHttpClient(lambda url: calls.append(url) or {"count": len(calls)})

    assert client.get_json("https://example.test/data", cache_ttl=0) == {"count": 1}
    assert client.get_json("https://example.test/data", cache_ttl=0) == {"count": 2}
    assert len(calls) == 2


def test_json_client_evicts_least_recently_used_entry() -> None:
    calls: list[str] = []
    client = JsonHttpClient(
        lambda url: calls.append(url) or {"url": url},
        max_cache_entries=2,
    )
    first = "https://example.test/first"
    second = "https://example.test/second"
    third = "https://example.test/third"

    client.get_json(first)
    client.get_json(second)
    client.get_json(first)
    client.get_json(third)
    client.get_json(first)
    client.get_json(second)

    assert calls == [first, second, third, second]


def test_json_client_rejects_negative_ttl() -> None:
    client = JsonHttpClient(lambda _: {})

    with pytest.raises(ValueError, match="cache_ttl cannot be negative"):
        client.get_json("https://example.test/data", cache_ttl=-1)


def test_json_client_reports_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"{not json"

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        del args, kwargs
        return FakeResponse()

    monkeypatch.setattr(networking, "urlopen", fake_urlopen)

    with pytest.raises(NetworkError, match="Could not fetch JSON"):
        networking._download_json("https://example.test/data")


def test_json_client_parses_floating_values_as_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"value":0.1234567890123456789}'

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        del args, kwargs
        return FakeResponse()

    monkeypatch.setattr(networking, "urlopen", fake_urlopen)

    assert networking._download_json("https://example.test/data") == {
        "value": Decimal("0.1234567890123456789")
    }
