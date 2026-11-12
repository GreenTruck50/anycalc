from decimal import Decimal
from typing import Callable

import flet as ft
import pytest

from currency_api import CurrencyApi
from currency_view import CurrencyConversionView


class StubPage:
    def update(self) -> None:
        pass


def build_view(
    fetch_json: Callable[[str], dict],
    saved_pair: tuple[str, str] | None = None,
    on_pair_changed: Callable[[str, str], None] | None = None,
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

    assert view.result_field.value == "91.2345678901234567"
    assert view.rate_date.value == "Rate date: 2026-11-03"
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
