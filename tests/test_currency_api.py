from decimal import Decimal

import pytest

import networking
from currency_api import CurrencyApi, CurrencyApiError


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
