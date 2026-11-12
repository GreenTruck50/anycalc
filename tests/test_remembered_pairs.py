"""The unit and currency pairs the pages reopen on.

Every conversion page and the currency page remember the two units / currencies
they were last left on and reopen on them - including across a restart, since the
pairs ride along in the saved app state. No app host is needed: the app is built
over the shared page stub in ``tests/stub_page.py``, the views are driven through
the handlers their own controls hold, and the storage layer itself is exercised
through ``decode_state`` / ``encode_state`` in ``tests/test_data_storage.py``.
Run this file with ``pytest -k pairs``.

Who owns what, and why the checks sit where they do:

* the view decides what to open on, because only it knows which units its own
  dropdowns offer - a saved pair naming a unit the data file no longer has has to
  fall back to the group's first two units rather than leave a dropdown showing a
  value its option list does not contain;
* the app decides what to remember, because a view owns no storage;
* a swap counts as a choice of pair like any other, which is what makes a pair
  change reachable from the app-host test in ``tests/test_app.py`` - that file
  cannot pick an arbitrary pair out of a ``Dropdown`` at all.
"""

import asyncio
import types
from typing import Any, Callable, cast

import flet as ft

from conversion_view import ConversionView
from conversions import load_conversion_config
from currency_view import CurrencyConversionView
from data_storage import AppState
from stub_page import StubPage, build_app, fire
from ui import AnycalcApp

UNIT_GROUPS, CONVERSION_OPTIONS = load_conversion_config()


def unit_group(name: str) -> dict[str, Any]:
    """The unit group behind a conversion menu entry."""

    return next(group for group in UNIT_GROUPS if group["name"] == name)


def conversion_entry(name: str) -> dict[str, Any]:
    """The conversion menu entry with this name."""

    return next(entry for entry in CONVERSION_OPTIONS if entry["name"] == name)


def make_copy_button(
    _get_value: Callable[[], str | None],
    *,
    tooltip: str,
) -> ft.IconButton:
    del _get_value
    return ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=tooltip)


def build_conversion_view(
    group_name: str,
    saved_pair: tuple[str, str] | None = None,
    on_units_changed: Callable[[str, str], None] | None = None,
) -> ConversionView:
    """The real form for one menu entry, over the shared page stub."""

    group = unit_group(group_name)
    view = ConversionView(
        cast(ft.Page, StubPage()),
        conversion_entry(f"{group_name} Conversion"),
        group["units"],
        {
            unit["id"]: f"{unit['name']} ({unit['symbol']})"
            for unit in group["units"]
        },
        make_copy_button,
        saved_pair=saved_pair,
        on_units_changed=on_units_changed,
    )
    view.build()
    return view


def select(view: ConversionView, dropdown: ft.Dropdown, unit_id: str) -> None:
    """Pick a unit the way the page does: the control already holds the new value
    when its ``on_select`` handler runs."""

    dropdown.value = unit_id
    fire(dropdown.on_select, types.SimpleNamespace())


def fire_async(handler: Callable[..., Any], *args: Any) -> None:
    """Run an async control handler to completion outside the page's loop."""

    result = handler(*args)
    if asyncio.iscoroutine(result):
        asyncio.run(result)


# --- what a conversion page opens on -----------------------------------------


def test_a_conversion_page_opens_on_the_first_two_units_of_its_group() -> None:
    view = build_conversion_view("Volume")
    units = unit_group("Volume")["units"]

    assert view.source_dropdown.value == units[0]["id"]
    assert view.target_dropdown.value == units[1]["id"]


def test_a_conversion_page_reopens_on_the_pair_it_was_last_left_on() -> None:
    view = build_conversion_view("Volume", saved_pair=("volume_cubic_meter", "volume_liter"))

    assert view.source_dropdown.value == "volume_cubic_meter"
    assert view.target_dropdown.value == "volume_liter"


def test_a_saved_pair_naming_a_lost_unit_falls_back_to_the_default_pair() -> None:
    units = unit_group("Volume")["units"]
    view = build_conversion_view("Volume", saved_pair=("volume_hogshead", "volume_liter"))

    assert view.source_dropdown.value == units[0]["id"]
    assert view.target_dropdown.value == units[1]["id"]


def test_the_saved_pair_of_one_group_is_not_used_by_another() -> None:
    """Pairs are keyed by conversion page, so Length never opens on Volume units."""

    units = unit_group("Length")["units"]
    view = build_conversion_view("Length", saved_pair=("volume_liter", "volume_ccf"))

    assert view.source_dropdown.value == units[0]["id"]
    assert view.target_dropdown.value == units[1]["id"]


# --- what a conversion page reports back -------------------------------------


def test_choosing_a_unit_reports_the_new_pair_to_the_app() -> None:
    reported: list[tuple[str, str]] = []
    view = build_conversion_view(
        "Volume",
        on_units_changed=lambda source, target: reported.append((source, target)),
    )

    select(view, view.target_dropdown, "volume_cubic_meter")

    assert reported == [(unit_group("Volume")["units"][0]["id"], "volume_cubic_meter")]


def test_swapping_units_reports_the_swapped_pair() -> None:
    reported: list[tuple[str, str]] = []
    view = build_conversion_view(
        "Volume",
        saved_pair=("volume_cubic_meter", "volume_liter"),
        on_units_changed=lambda source, target: reported.append((source, target)),
    )

    fire(view.swap_button.on_click, types.SimpleNamespace())

    assert reported == [("volume_liter", "volume_cubic_meter")]


# --- the app remembers, and hands the pair back on the next opening ----------


def shown_conversion_view(app: AnycalcApp) -> ConversionView:
    """The conversion form the app currently holds in the content area."""

    assert app.conversion_view is not None
    return app.conversion_view


def test_choosing_a_unit_puts_the_pair_in_the_saved_state() -> None:
    app = build_app()

    app.open_conversion(conversion_entry("Volume Conversion"))
    select(shown_conversion_view(app), shown_conversion_view(app).target_dropdown, "volume_ccf")

    assert app.unit_pairs == {
        "Volume Conversion": ("volume_cubic_millimeter", "volume_ccf")
    }
    assert app._state_snapshot().unit_pairs == (
        ("Volume Conversion", "volume_cubic_millimeter", "volume_ccf"),
    )
    assert "save_data" in app.page.tasks  # type: ignore[attr-defined]


def test_a_conversion_page_reopens_on_the_pair_it_was_left_on() -> None:
    app = build_app()
    entry = conversion_entry("Volume Conversion")

    app.open_conversion(entry)
    select(shown_conversion_view(app), shown_conversion_view(app).source_dropdown, "volume_liter")
    # Leave the page and come back, as closing the drawer and opening the entry
    # again does.
    app.open_conversion(conversion_entry("Length Conversion"))
    app.open_conversion(entry)

    assert shown_conversion_view(app).source_dropdown.value == "volume_liter"
    assert (
        shown_conversion_view(app).target_dropdown.value == "volume_cubic_centimeter"
    )


def test_each_page_keeps_its_own_pair() -> None:
    app = build_app()

    app.open_conversion(conversion_entry("Volume Conversion"))
    select(shown_conversion_view(app), shown_conversion_view(app).source_dropdown, "volume_ccf")
    app.open_conversion(conversion_entry("Length Conversion"))
    select(shown_conversion_view(app), shown_conversion_view(app).source_dropdown, "length_mile")

    assert app.unit_pairs == {
        "Volume Conversion": ("volume_ccf", "volume_cubic_centimeter"),
        "Length Conversion": ("length_mile", "length_micrometer"),
    }


def test_re_choosing_a_pair_already_remembered_saves_nothing_new() -> None:
    app = build_app()
    app.open_conversion(conversion_entry("Volume Conversion"))
    view = shown_conversion_view(app)
    select(view, view.target_dropdown, "volume_ccf")
    saves_before = app.page.tasks.count("save_data")  # type: ignore[attr-defined]

    select(view, view.target_dropdown, "volume_ccf")

    assert app.page.tasks.count("save_data") == saves_before  # type: ignore[attr-defined]
    assert app.unit_pairs == {
        "Volume Conversion": ("volume_cubic_millimeter", "volume_ccf")
    }


def test_a_restored_save_hands_its_pairs_to_the_pages() -> None:
    class StubStore:
        async def load(self) -> AppState:
            return AppState(
                "Dark",
                (),
                unit_pairs=(("Volume Conversion", "volume_ccf", "volume_liter"),),
                currency_pair=("jpy", "chf"),
            )

        async def save(self, state: AppState, include_pi: bool = False) -> None:
            del state, include_pi

        async def clear(self) -> None:
            pass

    app = build_app()
    app.data_store = StubStore()  # type: ignore[assignment]
    asyncio.run(app.load_saved_data())

    assert app.currency_pair == ("jpy", "chf")
    app.open_conversion(conversion_entry("Volume Conversion"))
    assert shown_conversion_view(app).source_dropdown.value == "volume_ccf"
    assert shown_conversion_view(app).target_dropdown.value == "volume_liter"


def test_the_currency_page_is_handed_the_pair_the_save_remembered() -> None:
    class StubStore:
        async def load(self) -> AppState:
            return AppState("Dark", (), currency_pair=("jpy", "chf"))

        async def save(self, state: AppState, include_pi: bool = False) -> None:
            del state, include_pi

        async def clear(self) -> None:
            pass

    app = build_app()
    app.data_store = StubStore()  # type: ignore[assignment]
    asyncio.run(app.load_saved_data())

    app.open_currency_conversion()

    assert app.currency_view is not None
    assert app.currency_view.saved_pair == ("jpy", "chf")


def test_resetting_the_app_data_forgets_the_pairs() -> None:
    app = build_app()
    app.unit_pairs["Volume Conversion"] = ("volume_ccf", "volume_liter")
    app.currency_pair = ("jpy", "chf")

    app.reset_app_data()

    assert app.unit_pairs == {}
    assert app.currency_pair is None
    assert app._state_snapshot().unit_pairs == ()
    assert app._state_snapshot().currency_pair is None


# --- the currency page reports its pair changes ------------------------------


def test_the_currency_page_reports_a_changed_pair() -> None:
    reported: list[tuple[str, str]] = []

    class StubApi:
        def get_currencies(self) -> dict[str, str]:
            return {"usd": "US Dollar", "eur": "Euro", "jpy": "Japanese Yen"}

        def get_rates(self, source: str):
            del source
            raise AssertionError("no amount is typed, so no rate may be fetched")

    view = CurrencyConversionView(
        StubPage(),  # type: ignore[arg-type]
        make_copy_button,
        StubApi(),  # type: ignore[arg-type]
        on_pair_changed=lambda source, target: reported.append((source, target)),
    )
    view.build()
    fire_async(view.load_currencies)

    view.target_dropdown.value = "jpy"
    fire_async(view.select_currency, types.SimpleNamespace())

    assert reported == [("usd", "jpy")]
