"""Client for the daily rates published by fawazahmed0/exchange-api."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from http.client import HTTPException
import re
from typing import Any, Callable

from networking import NetworkError, get_json

_PRIMARY_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/"
_FALLBACK_URL = "https://latest.currency-api.pages.dev/"
_CURRENCY_CODE = re.compile(r"[a-z0-9]+\Z")
_RATE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_CURRENCY_DATA_CACHE_TTL_SECONDS = 24 * 60 * 60
# A rate table served from the saved copy has to divide one published rate by
# another, which the app's process-wide Decimal precision (500 digits) would
# expand into a wall of digits. The API itself publishes about fifteen, so a
# derived rate is computed to that many significant digits and no further.
_DERIVED_RATE_SIGNIFICANT_DIGITS = 15


class CurrencyApiError(RuntimeError):
    """Raised when neither exchange API host can provide usable data."""


@dataclass(frozen=True)
class CurrencyRates:
    date: str
    rates: dict[str, Decimal]


@dataclass(frozen=True)
class SavedCurrencyRates:
    """The last rate table the exchange API served, kept for when it does not.

    Rates travel as text so a save round-trips exactly the decimal the API
    published, and the table is a tuple of pairs rather than a dict for the reason
    the saved history and unit pairs have: the app state carrying it stays
    hashable and JSON round-trips.
    """

    base: str
    date: str
    rates: tuple[tuple[str, str], ...]


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


def as_saved_currency_rates(base: str, rates: CurrencyRates) -> SavedCurrencyRates:
    """The storable form of a table the API just served."""

    return SavedCurrencyRates(
        _validate_currency_code(base),
        rates.date,
        tuple((code, str(rate)) for code, rate in rates.rates.items()),
    )


def rates_from_saved(saved: SavedCurrencyRates, base: str) -> CurrencyRates:
    """A rate table for ``base`` rebuilt from the last one that was saved.

    One published table prices every currency in it against every other, so a
    table for the base it was fetched for is used as it stands and any other base
    is derived from it: the saved USD table's JPY rate over its GBP rate is the
    JPY price of one GBP. Derived rates are computed to the number of significant
    digits the API itself publishes, so an offline answer is no longer than a
    live one.
    """

    requested = _validate_currency_code(base)
    stored_base = _validate_currency_code(saved.base)
    if not _RATE_DATE.fullmatch(saved.date):
        raise CurrencyApiError("The saved exchange rates have no valid date.")
    try:
        date.fromisoformat(saved.date)
    except ValueError:
        # The shape is right but it is not a day on a calendar - "2026-13-45".
        raise CurrencyApiError("The saved exchange rates have no valid date.") from None
    rates: dict[str, Decimal] = {
        _validate_currency_code(code): _validate_rate(code, raw_rate)
        for code, raw_rate in saved.rates
    }
    if not rates:
        raise CurrencyApiError("The saved exchange rates are empty.")
    if requested == stored_base:
        return CurrencyRates(saved.date, rates)

    pivot = rates.get(requested)
    if pivot is None:
        raise CurrencyApiError(
            f"The saved exchange rates have no {requested.upper()} rate."
        )
    with localcontext() as context:
        context.prec = _DERIVED_RATE_SIGNIFICANT_DIGITS
        derived = {code: value / pivot for code, value in rates.items()}
    return CurrencyRates(saved.date, derived)


def rate_age_in_days(rate_date: str, today: date) -> int:
    """How many days between a rate date and today (never a negative count).

    A date that is not a real calendar date - only a hand-edited save can produce
    one, both providers' dates are checked before they get this far - is reported
    as a day old, so a corrupt date warns rather than looking current.
    """

    try:
        published = date.fromisoformat(rate_date)
    except ValueError:
        return 1
    return max(0, (today - published).days)


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

    rate_date = payload.get("date")
    rates_data = payload.get(base_currency)
    if not isinstance(rate_date, str) or not _RATE_DATE.fullmatch(rate_date):
        raise CurrencyApiError("The exchange-rate response has no valid rate date.")
    if not isinstance(rates_data, dict) or not rates_data:
        raise CurrencyApiError(
            f"The exchange-rate response has no rates for {base_currency.upper()}."
        )

    rates: dict[str, Decimal] = {}
    for raw_code, raw_rate in rates_data.items():
        code = _validate_currency_code(raw_code)
        rates[code] = _validate_rate(code, raw_rate)
    return CurrencyRates(rate_date, rates)


def _validate_rate(code: str, raw_rate: Any) -> Decimal:
    """One rate, whether it came from a response or from a saved table."""

    if isinstance(raw_rate, bool):
        raise CurrencyApiError(f"The rate for {code.upper()} is invalid.")
    try:
        rate = raw_rate if isinstance(raw_rate, Decimal) else Decimal(str(raw_rate))
    except (InvalidOperation, ValueError):
        raise CurrencyApiError(f"The rate for {code.upper()} is invalid.") from None
    if not rate.is_finite() or rate <= 0:
        raise CurrencyApiError(f"The rate for {code.upper()} is invalid.")
    return rate


def _validate_currency_code(code: Any) -> str:
    if not isinstance(code, str):
        raise CurrencyApiError("A currency code must be text.")
    normalized = code.lower()
    if not _CURRENCY_CODE.fullmatch(normalized):
        raise CurrencyApiError(f"Invalid currency code: {code!r}.")
    return normalized
