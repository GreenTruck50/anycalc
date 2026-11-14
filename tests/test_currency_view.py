from datetime import date
from decimal import Decimal
from typing import Callable

import flet as ft
import pytest

from currency_api import CurrencyApi, SavedCurrencyRates
import currency_view
from currency_view import CurrencyConversionView


class StubPage:
    def update(self) -> None:
        pass


def build_view(
    fetch_json: Callable[[str], dict],
    saved_pair: tuple[str, str] | None = None,
    on_pair_changed: Callable[[str, str], None] | None = None,
    saved_currencies: dict[str, str] | None = None,
    saved_rates: SavedCurrencyRates | None = None,
    on_currencies_loaded: Callable[[dict[str, str]], None] | None = None,
    on_rates_saved: Callable[[SavedCurrencyRates], None] | None = None,
    today: Callable[[], date] = lambda: date(2026, 11, 13),
) -> tuple[CurrencyConversionView, list[str]]:
    requested_urls: list[str] = []

    def recording_fetch(url: str):
        requested_urls.append(url)
        return fetch_json(url)

    def make_copy_button(
        _get_value: Callable[[], str | None],
        *,
        tooltip: str,
    ) -> ft.IconButton:
        del _get_value
        return ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=tooltip)

    view = CurrencyConversionView(
        StubPage(),
        make_copy_button,
        CurrencyApi(recording_fetch),
        saved_pair=saved_pair,
        on_pair_changed=on_pair_changed,
        saved_currencies=saved_currencies,
        saved_rates=saved_rates,
        on_currencies_loaded=on_currencies_loaded,
        on_rates_saved=on_rates_saved,
        today=today,
    )
    view.build()
    return view, requested_urls


@pytest.mark.asyncio
async def test_currency_view_loads_and_converts_using_rates_date() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {
            "date": "2026-11-03",
            "usd": {
                "usd": Decimal("1"),
                "eur": Decimal("0.912345678901234567"),
            },
        }

    view, requested_urls = build_view(fetch_json)

    await view.load_currencies()
    assert view.source_dropdown.value == "usd"
    assert view.target_dropdown.value == "eur"
    assert view.status.value == "2 currencies available."

    view.input_field.value = "100"
    await view.run_conversion()

    # 100 x 0.912345678901234567 at the app's twelve-significant-digit default.
    assert view.result_field.value == "91.2345678901"
    assert view.rate_date.value == "Rates as of 2026-11-03"
    assert view.rate_date.visible is True
    assert view.staleness.visible is True
    assert view.staleness_text.value == "10 days old"
    assert requested_urls == [
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/"
        "v1/currencies.min.json",
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/"
        "v1/currencies/usd.min.json",
    ]


@pytest.mark.asyncio
async def test_currency_view_does_not_fetch_rates_for_empty_amount() -> None:
    def fetch_json(url: str) -> dict:
        del url
        return {"usd": "US Dollar", "eur": "Euro"}

    view, requested_urls = build_view(fetch_json)

    await view.load_currencies()
    await view.run_conversion()

    assert view.result_field.value == ""
    assert len(requested_urls) == 1


@pytest.mark.asyncio
async def test_amount_entered_while_currencies_load_is_converted_afterward() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {
            "date": "2026-11-03",
            "usd": {"eur": Decimal("0.9")},
        }

    view, _ = build_view(fetch_json)
    view.input_field.value = "10"

    await view.load_currencies()

    assert view.result_field.value == "9"


# --- the pair the page opens on ----------------------------------------------


@pytest.mark.asyncio
async def test_the_currency_page_reopens_on_the_pair_it_was_last_left_on() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {
                "usd": "US Dollar",
                "eur": "Euro",
                "jpy": "Japanese Yen",
                "chf": "Swiss Franc",
            }
        return {"date": "2026-11-03", "jpy": {"chf": Decimal("0.0058")}}

    view, _ = build_view(fetch_json, saved_pair=("jpy", "chf"))

    await view.load_currencies()

    assert view.source_dropdown.value == "jpy"
    assert view.target_dropdown.value == "chf"


@pytest.mark.asyncio
async def test_a_saved_pair_the_api_dropped_falls_back_to_usd_and_eur() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {"date": "2026-11-03", "usd": {"eur": Decimal("0.9")}}

    view, _ = build_view(fetch_json, saved_pair=("jpy", "chf"))

    await view.load_currencies()

    assert view.source_dropdown.value == "usd"
    assert view.target_dropdown.value == "eur"


@pytest.mark.asyncio
async def test_swapping_currencies_reports_the_swapped_pair() -> None:
    reported: list[tuple[str, str]] = []

    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {"date": "2026-11-03", "eur": {"usd": Decimal("1.1")}}

    view, _ = build_view(
        fetch_json,
        on_pair_changed=lambda source, target: reported.append((source, target)),
    )
    await view.load_currencies()

    await view.swap_currencies(None)

    assert reported == [("eur", "usd")]


# --- how current the rates on screen are --------------------------------------
#
# `build_view` holds the clock still at 2026-11-13, so a test can say what a rate
# date is worth without waiting for a calendar.


def offline_fetch(url: str) -> dict:
    """A client that behaves like neither exchange host answering."""

    raise OSError(f"no route to {url}")


@pytest.mark.asyncio
async def test_current_live_rates_need_no_badge() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {"date": "2026-11-13", "usd": {"eur": Decimal("0.9")}}

    view, _ = build_view(fetch_json)
    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    assert view.rate_date.value == "Rates as of 2026-11-13"
    assert view.staleness.visible is False
    assert view.status.value == ""


@pytest.mark.asyncio
async def test_a_rate_table_one_day_old_says_so() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {"date": "2026-11-12", "usd": {"eur": Decimal("0.9")}}

    view, _ = build_view(fetch_json)
    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    assert view.rate_date.value == "Rates as of 2026-11-12"
    assert view.staleness.visible is True
    assert view.staleness_text.value == "1 day old"


@pytest.mark.asyncio
async def test_a_live_fetch_is_handed_to_the_app_for_saving() -> None:
    lists: list[dict[str, str]] = []
    tables: list[SavedCurrencyRates] = []

    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        return {"date": "2026-11-12", "usd": {"eur": Decimal("0.9")}}

    view, _ = build_view(
        fetch_json,
        on_currencies_loaded=lists.append,
        on_rates_saved=tables.append,
    )
    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    assert lists == [{"usd": "US Dollar", "eur": "Euro"}]
    assert tables == [SavedCurrencyRates("usd", "2026-11-12", (("eur", "0.9"),))]


# --- the offline fallback ------------------------------------------------------


@pytest.mark.asyncio
async def test_the_page_opens_on_the_saved_currency_list_when_the_api_is_down() -> None:
    view, _ = build_view(
        offline_fetch,
        saved_currencies={"usd": "US Dollar", "eur": "Euro"},
    )

    await view.load_currencies()

    assert view.status.value == "2 currencies from the last saved list."
    assert view.status.color == currency_view.STALENESS_TEXT
    assert view.retry_button.visible is True
    assert [option.key for option in view.source_dropdown.options] == ["eur", "usd"]


@pytest.mark.asyncio
async def test_the_page_converts_from_the_saved_rates_when_the_api_is_down() -> None:
    saved = SavedCurrencyRates("usd", "2026-11-10", (("usd", "1"), ("eur", "0.9")))
    view, _ = build_view(
        offline_fetch,
        saved_currencies={"usd": "US Dollar", "eur": "Euro"},
        saved_rates=saved,
    )

    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    assert view.result_field.error is None
    assert view.result_field.value == "90"
    assert view.rate_date.value == "Rates as of 2026-11-10"
    assert (
        view.status.value
        == "Live rates are unavailable - converting with the last saved rates."
    )
    assert view.status.color == currency_view.STALENESS_TEXT
    assert view.staleness.visible is True
    assert view.staleness_text.value == "Last known — 3 days old"


@pytest.mark.asyncio
async def test_the_saved_table_prices_a_pair_it_was_not_fetched_for() -> None:
    saved = SavedCurrencyRates(
        "usd", "2026-11-10", (("usd", "1"), ("eur", "0.9"), ("jpy", "150"))
    )
    view, _ = build_view(
        offline_fetch,
        saved_pair=("jpy", "eur"),
        saved_currencies={"usd": "US Dollar", "eur": "Euro", "jpy": "Japanese Yen"},
        saved_rates=saved,
    )

    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    # The saved USD table priced 0.9 euros and 150 yen to the dollar, so a euro is
    # worth 150 / 0.9 yen - a pair that never had a table fetched for it.
    assert view.result_field.value == "0.6"


@pytest.mark.asyncio
async def test_an_offline_run_offers_nothing_back_to_be_saved() -> None:
    lists: list[dict[str, str]] = []
    tables: list[SavedCurrencyRates] = []
    saved = SavedCurrencyRates("usd", "2026-11-10", (("eur", "0.9"),))

    view, _ = build_view(
        offline_fetch,
        saved_currencies={"usd": "US Dollar", "eur": "Euro"},
        saved_rates=saved,
        on_currencies_loaded=lists.append,
        on_rates_saved=tables.append,
    )

    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    # Handing the saved table back would age the save without learning anything.
    assert lists == []
    assert tables == []


@pytest.mark.asyncio
async def test_a_pair_the_saved_table_cannot_price_says_why() -> None:
    saved = SavedCurrencyRates("usd", "2026-11-10", (("usd", "1"), ("eur", "0.9")))
    view, _ = build_view(
        offline_fetch,
        saved_pair=("gbp", "eur"),
        saved_currencies={"usd": "US Dollar", "eur": "Euro", "gbp": "British Pound"},
        saved_rates=saved,
    )

    await view.load_currencies()
    view.input_field.value = "100"
    await view.run_conversion()

    assert view.result_field.error == "The saved exchange rates have no GBP rate."
    assert view.staleness.visible is False


@pytest.mark.asyncio
async def test_a_failed_currency_list_with_nothing_saved_still_fails_loudly() -> None:
    view, _ = build_view(offline_fetch)

    await view.load_currencies()

    assert "Could not load exchange data" in str(view.status.value)
    assert view.status.color == ft.Colors.RED_400
    assert view.retry_button.visible is True


@pytest.mark.asyncio
async def test_a_failed_rate_with_nothing_saved_still_fails_loudly() -> None:
    def fetch_json(url: str) -> dict:
        if url.endswith("/v1/currencies.min.json"):
            return {"usd": "US Dollar", "eur": "Euro"}
        raise OSError("no route to the rate host")

    view, _ = build_view(fetch_json)
    await view.load_currencies()
    view.input_field.value = "100"

    await view.run_conversion()

    assert view.result_field.value == ""
    assert "Could not load exchange data" in str(view.result_field.error or "")
    assert view.status.value == ""
    assert view.rate_date.visible is False

