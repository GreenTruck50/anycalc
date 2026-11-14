from datetime import date
from decimal import Decimal

import pytest

import networking
from currency_api import (
    CurrencyApi,
    CurrencyApiError,
    CurrencyRates,
    SavedCurrencyRates,
    as_saved_currency_rates,
    rate_age_in_days,
    rates_from_saved,
)


PRIMARY = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/"
FALLBACK = "https://latest.currency-api.pages.dev/"


def test_currency_list_uses_minified_endpoint_and_caches() -> None:
    calls: list[str] = []
    api = CurrencyApi(
        lambda url: calls.append(url) or {"usd": "US Dollar", "eurc": ""}
    )

    assert api.get_currencies() == {"usd": "US Dollar", "eurc": "EURC"}
    assert api.get_currencies() == {"usd": "US Dollar", "eurc": "EURC"}
    assert calls == [f"{PRIMARY}v1/currencies.min.json"]


def test_rates_use_minified_endpoint_and_keep_decimal_precision() -> None:
    calls: list[str] = []
    api = CurrencyApi(
        lambda url: calls.append(url)
        or {
            "date": "2026-11-03",
            "usd": {"usd": 1, "eur": Decimal("0.912345678901234567")},
        }
    )

    result = api.get_rates("USD")
    assert result.date == "2026-11-03"
    assert result.rates["eur"] == Decimal("0.912345678901234567")
    assert result.rates["eur"] * Decimal("100") == Decimal("91.234567890123456700")
    assert api.get_rates("usd") == result
    assert calls == [f"{PRIMARY}v1/currencies/usd.min.json"]


def test_falls_back_to_cloudflare_when_primary_fails() -> None:
    calls: list[str] = []

    def fetch_json(url: str) -> dict:
        calls.append(url)
        if url.startswith(PRIMARY):
            raise OSError("primary unavailable")
        return {"usd": "US Dollar"}

    api = CurrencyApi(fetch_json)

    assert api.get_currencies() == {"usd": "US Dollar"}
    assert calls == [
        f"{PRIMARY}v1/currencies.min.json",
        f"{FALLBACK}v1/currencies.min.json",
    ]


def test_falls_back_when_primary_returns_invalid_rate_data() -> None:
    calls: list[str] = []

    def fetch_json(url: str) -> dict:
        calls.append(url)
        if url.startswith(PRIMARY):
            return {"date": "invalid", "usd": {"eur": 0.9}}
        return {"date": "2026-11-03", "usd": {"eur": Decimal("0.9")}}

    api = CurrencyApi(fetch_json)

    assert api.get_rates("usd").rates["eur"] == Decimal("0.9")
    assert calls == [
        f"{PRIMARY}v1/currencies/usd.min.json",
        f"{FALLBACK}v1/currencies/usd.min.json",
    ]


def test_reports_both_provider_failures() -> None:
    def fetch_json(url: str) -> dict:
        raise OSError(f"unavailable: {url}")

    api = CurrencyApi(fetch_json)

    with pytest.raises(CurrencyApiError) as error:
        api.get_currencies()

    assert "jsDelivr" in str(error.value)
    assert "Cloudflare fallback" in str(error.value)


def test_rejects_invalid_currency_code_before_requesting() -> None:
    api = CurrencyApi(lambda _: pytest.fail("invalid code must not be requested"))

    with pytest.raises(CurrencyApiError, match="Invalid currency code"):
        api.get_rates("../usd")


def test_rejects_non_positive_exchange_rate() -> None:
    api = CurrencyApi(
        lambda _: {"date": "2026-11-03", "usd": {"eur": Decimal("0")}}
    )

    with pytest.raises(CurrencyApiError, match="rate for EUR is invalid"):
        api.get_rates("usd")


def test_urllib_loader_parses_json_rates_as_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"date":"2026-11-03","usd":{"eur":0.912345678901234567}}'

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        assert request.full_url == f"{PRIMARY}v1/currencies/usd.min.json"
        assert timeout == 10
        return FakeResponse()

    monkeypatch.setattr(networking, "urlopen", fake_urlopen)

    payload = networking._download_json(f"{PRIMARY}v1/currencies/usd.min.json")

    assert payload["usd"]["eur"] == Decimal("0.912345678901234567")

# --- the last rate table the app kept -----------------------------------------


def kept_table() -> SavedCurrencyRates:
    """A USD table as it would come back out of client storage."""

    return SavedCurrencyRates(
        "usd",
        "2026-11-10",
        (("usd", "1"), ("eur", "0.9"), ("jpy", "150")),
    )


def test_a_served_table_is_storable_without_losing_digits() -> None:
    served = CurrencyRates(
        "2026-11-10", {"eur": Decimal("0.912345678901234567")}
    )

    saved = as_saved_currency_rates("USD", served)

    assert saved == SavedCurrencyRates(
        "usd", "2026-11-10", (("eur", "0.912345678901234567"),)
    )


def test_a_kept_table_serves_its_own_base_exactly() -> None:
    rates = rates_from_saved(kept_table(), "usd")

    assert rates.date == "2026-11-10"
    assert rates.rates["eur"] == Decimal("0.9")
    assert rates.rates["jpy"] == Decimal("150")


def test_a_kept_table_prices_any_pair_inside_it() -> None:
    rates = rates_from_saved(kept_table(), "eur")

    assert rates.date == "2026-11-10"
    assert rates.rates["eur"] == Decimal("1")
    assert rates.rates["usd"] == Decimal("1.11111111111111")
    assert rates.rates["jpy"] == Decimal("166.666666666667")


def test_a_kept_table_without_the_base_asked_for_cannot_serve_it() -> None:
    with pytest.raises(CurrencyApiError, match="have no GBP rate"):
        rates_from_saved(kept_table(), "gbp")


def test_kept_rates_are_checked_as_hard_as_live_ones() -> None:
    broken = [
        (SavedCurrencyRates("usd", "yesterday", (("eur", "0.9"),)), "no valid date"),
        (SavedCurrencyRates("usd", "2026-13-45", (("eur", "0.9"),)), "no valid date"),
        (SavedCurrencyRates("usd", "2026-11-10", ()), "are empty"),
        (SavedCurrencyRates("usd", "2026-11-10", (("eur", "-1"),)), "EUR is invalid"),
        (SavedCurrencyRates("usd", "2026-11-10", (("eur", "nonsense"),)), "EUR is invalid"),
        (SavedCurrencyRates("usd", "2026-11-10", (("../x", "1"),)), "Invalid currency code"),
        (SavedCurrencyRates("../usd", "2026-11-10", (("eur", "1"),)), "Invalid currency code"),
    ]

    for saved, message in broken:
        with pytest.raises(CurrencyApiError, match=message):
            rates_from_saved(saved, "usd")


def test_rate_age_counts_days_from_the_rate_date() -> None:
    assert rate_age_in_days("2026-11-13", date(2026, 11, 13)) == 0
    assert rate_age_in_days("2026-11-10", date(2026, 11, 13)) == 3
    assert rate_age_in_days("2026-11-14", date(2026, 11, 13)) == 0


def test_a_rate_date_that_is_not_a_day_on_a_calendar_warns() -> None:
    assert rate_age_in_days("2026-13-45", date(2026, 11, 13)) == 1

