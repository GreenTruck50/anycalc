"""Client for the daily rates published by fawazahmed0/exchange-api."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
import re
from typing import Any, Callable

from networking import NetworkError, get_json

_PRIMARY_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/"
_FALLBACK_URL = "https://latest.currency-api.pages.dev/"
_CURRENCY_CODE = re.compile(r"[a-z0-9]+\Z")
_RATE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_CURRENCY_DATA_CACHE_TTL_SECONDS = 24 * 60 * 60


class CurrencyApiError(RuntimeError):
    """Raised when neither exchange API host can provide usable data."""


@dataclass(frozen=True)
class CurrencyRates:
    date: str
    rates: dict[str, Decimal]


class CurrencyApi:
    """Fetch and cache minified currency names and per-base exchange rates."""

    def __init__(
        self,
        fetch_json: Callable[[str], Any] | None = None,
    ) -> None:
        self._fetch_json = (
            fetch_json
            if fetch_json is not None
            else lambda url: get_json(
                url,
                cache_ttl=_CURRENCY_DATA_CACHE_TTL_SECONDS,
            )
        )
        self._currencies: dict[str, str] | None = None
        self._rates: dict[str, CurrencyRates] = {}

    def get_currencies(self) -> dict[str, str]:
        currencies = self._currencies
        if currencies is None:
            currencies = self._request(
                "v1/currencies.min.json",
                _validate_currencies,
            )
            self._currencies = currencies
        return currencies.copy()

    def get_rates(self, base_currency: str) -> CurrencyRates:
        base = _validate_currency_code(base_currency)
        if base not in self._rates:
            self._rates[base] = self._request(
                f"v1/currencies/{base}.min.json",
                lambda payload: _validate_rates(payload, base),
            )
        rates = self._rates[base]
        return CurrencyRates(rates.date, rates.rates.copy())

    def _request(
        self,
        endpoint: str,
        validator: Callable[[Any], Any],
    ) -> Any:
        failures: list[str] = []
        for provider, root in (
            ("jsDelivr", _PRIMARY_URL),
            ("Cloudflare fallback", _FALLBACK_URL),
        ):
            try:
                return validator(self._fetch_json(f"{root}{endpoint}"))
            except (
                CurrencyApiError,
                NetworkError,
                OSError,
                TimeoutError,
                HTTPException,
            ) as error:
                failures.append(f"{provider}: {error}")

        raise CurrencyApiError(
            "Could not load exchange data. " + " ".join(failures)
        )


def _validate_currencies(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict) or not payload:
        raise CurrencyApiError("The currency list has an invalid format.")

    currencies: dict[str, str] = {}
    for raw_code, name in payload.items():
        code = _validate_currency_code(raw_code)
        if not isinstance(name, str):
            raise CurrencyApiError(f"The currency name for {code.upper()} is invalid.")
        currencies[code] = name.strip() or code.upper()
    return currencies


def _validate_rates(payload: Any, base_currency: str) -> CurrencyRates:
    if not isinstance(payload, dict):
        raise CurrencyApiError("The exchange-rate response has an invalid format.")

    date = payload.get("date")
    rates_data = payload.get(base_currency)
    if not isinstance(date, str) or not _RATE_DATE.fullmatch(date):
        raise CurrencyApiError("The exchange-rate response has no valid rate date.")
    if not isinstance(rates_data, dict) or not rates_data:
        raise CurrencyApiError(
            f"The exchange-rate response has no rates for {base_currency.upper()}."
        )

    rates: dict[str, Decimal] = {}
    for raw_code, raw_rate in rates_data.items():
        code = _validate_currency_code(raw_code)
        if isinstance(raw_rate, bool):
            raise CurrencyApiError(f"The rate for {code.upper()} is invalid.")
        try:
            rate = raw_rate if isinstance(raw_rate, Decimal) else Decimal(str(raw_rate))
        except (InvalidOperation, ValueError):
            raise CurrencyApiError(f"The rate for {code.upper()} is invalid.") from None
        if not rate.is_finite() or rate <= 0:
            raise CurrencyApiError(f"The rate for {code.upper()} is invalid.")
        rates[code] = rate
    return CurrencyRates(date, rates)


def _validate_currency_code(code: Any) -> str:
    if not isinstance(code, str):
        raise CurrencyApiError("A currency code must be text.")
    normalized = code.lower()
    if not _CURRENCY_CODE.fullmatch(normalized):
        raise CurrencyApiError(f"Invalid currency code: {code!r}.")
    return normalized
