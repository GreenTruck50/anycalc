"""Every dropdown in the app filters its own list, and a typed query that never
turned into a pick is settled the moment the box loses focus.

The unit menus are what this is for - the Volume group alone has 42 units and
``conversions.yaml`` runs to 2778 lines - but the filter is on every box, which is
what the user asked for, so the first test here walks the whole app and refuses any
dropdown that does not offer it.

No app host is needed: ``flet test`` cannot reach a ``Dropdown``'s options at all
(see the header notes of ``tests/test_app.py``), so the flags and the blur rule are
checked over the shared page stub in ``tests/stub_page.py``, driving the handlers
the controls themselves hold. What only a real window can show - the menu actually
narrowing as someone types - is checked by hand.

Run this file with ``pytest tests/test_dropdown_filter.py`` — a ``-k`` selector goes
by test names, not file names, and only one of the seven names here contains
"dropdown".
"""

import types
from typing import Any, Callable, cast

import flet as ft

from conversion_view import ConversionView
from conversions import load_conversion_config
from currency_view import CurrencyConversionView
from dropdowns import has_filter
from stub_page import StubPage, build_app, fire
from variable_dialogs import open_set_variable_dialog

UNIT_GROUPS, CONVERSION_OPTIONS = load_conversion_config()


def conversion_entry(name: str) -> dict[str, Any]:
    """The conversion menu entry with this name."""

    return next(entry for entry in CONVERSION_OPTIONS if entry["name"] == name)


def unit_group(name: str) -> dict[str, Any]:
    """The unit group behind a conversion menu entry."""

    return next(group for group in UNIT_GROUPS if group["name"] == name)


def make_copy_button(
    _get_value: Callable[[], str | None],
    *,
    tooltip: str,
) -> ft.IconButton:
    del _get_value
    return ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=tooltip)


def build_conversion_view(name: str = "Volume") -> ConversionView:
    """The real conversion form, over the shared page stub."""

    group = unit_group(name)
    view = ConversionView(
        cast(ft.Page, StubPage()),
        conversion_entry(f"{name} Conversion"),
        group["units"],
        {
            unit["id"]: f"{unit['name']} ({unit['symbol']})"
            for unit in group["units"]
        },
        make_copy_button,
    )
    view.build()
    return view


def build_currency_view() -> CurrencyConversionView:
    """The real currency form with a stub rate table."""

    class StubApi:
        def get_currencies(self) -> dict[str, str]:
            return {
                "usd": "US Dollar",
                "eur": "Euro",
                "chf": "Swiss Franc",
                "jpy": "Japanese Yen",
            }

        def get_rates(self, source: str):
            del source
            raise AssertionError("no amount is typed, so no rate may be fetched")

    view = CurrencyConversionView(
        StubPage(),  # type: ignore[arg-type]
        make_copy_button,
        StubApi(),  # type: ignore[arg-type]
    )
    view.build()
    return view


def collect_dropdowns(control: object) -> list[ft.Dropdown]:
    """Every ``Dropdown`` in a control tree, however it is nested.

    Children live in ``controls`` for the containers that hold several and in
    ``content`` for the ones that hold one; options are not controls and are left
    alone.
    """

    found: list[ft.Dropdown] = []
    pending: list[object] = [control]
    while pending:
        current = pending.pop()
        if isinstance(current, ft.Dropdown):
            found.append(current)
            continue
        children = getattr(current, "controls", None) or []
        content = getattr(current, "content", None)
        pending.extend([*children, *([content] if content is not None else [])])
    return found


def type_into(dropdown: ft.Dropdown, text: str) -> None:
    """Type into a searchable box the way the client does.

    The control already carries the typed words when its ``on_text_change``
    handler runs, which is the only thing that keeps the app's copy of the query
    current.
    """

    dropdown.text = text
    fire(dropdown.on_text_change, types.SimpleNamespace(control=dropdown))


def blur(dropdown: ft.Dropdown) -> None:
    """Take the caret out of the box, which is where the query gets settled."""

    fire(dropdown.on_blur, types.SimpleNamespace(control=dropdown))


# --- every box offers the filter ------------------------------------------------


def test_every_dropdown_the_app_builds_offers_its_filter() -> None:
    """No box is left out: the filter is on the whole app, not just the units."""

    app = build_app()
    roots: list[object] = [
        *app.page.controls,  # type: ignore[attr-defined]
        app.page.drawer,
        app.page.end_drawer,
        app.build_settings_dialog(),
    ]

    app.open_conversion(conversion_entry("Volume Conversion"))
    assert app.conversion_view is not None
    roots.append(app.conversion_view.build())
    app.open_currency_conversion()
    assert app.currency_view is not None
    roots.append(app.currency_view.build())
    app.open_pi()
    assert app.pi_view is not None
    roots.append(app.pi_view.build())
    open_set_variable_dialog(app)
    roots.extend(app.page.dialogs)  # type: ignore[attr-defined]

    dropdowns = [found for root in roots for found in collect_dropdowns(root)]
    assert len(dropdowns) >= 12, "the walk found too few boxes to trust it"
    missing = [
        dropdown.key or "<unnamed>"
        for dropdown in dropdowns
        if not has_filter(dropdown)
    ]
    assert missing == []

    keyed = {dropdown.key for dropdown in dropdowns}
    for expected in (
        "conversion-from",
        "conversion-to",
        "currency-from",
        "currency-to",
        "pi-digits",
        "settings-theme-dropdown",
        "settings-precision-decimals",
        "settings-precision-significant-figures",
        "settings-precision-scientific-notation",
        "settings-precision-rounding",
        "settings-history-length",
    ):
        assert expected in keyed, f"{expected} was never reached by the walk"


def test_the_long_lists_advertise_the_search() -> None:
    """The boxes worth searching show a magnifier; a three-choice box does not."""

    view = build_conversion_view()
    assert view.source_dropdown.leading_icon == ft.Icons.SEARCH
    assert view.target_dropdown.leading_icon == ft.Icons.SEARCH
    assert build_currency_view().source_dropdown.leading_icon == ft.Icons.SEARCH

    app = build_app()
    app.build_settings_dialog()
    assert app.settings_theme_dropdown.leading_icon is None


# --- a query that never became a pick ------------------------------------------


def test_typing_a_unit_and_blurring_picks_the_option_it_matches() -> None:
    """One option matching the query means that option, without opening the menu."""

    view = build_conversion_view()
    reported: list[tuple[str, str]] = []
    view.on_units_changed = lambda source, target: reported.append((source, target))

    view.input_field.value = "3"
    type_into(view.target_dropdown, "ccf")
    blur(view.target_dropdown)

    assert view.target_dropdown.value == "volume_ccf"
    # The view's own on_select ran, so the pair was remembered and the amount
    # re-converted - a resolved pick is a pick.
    assert reported == [("volume_cubic_millimeter", "volume_ccf")]
    assert view.result_field.value != ""


def test_a_query_matching_several_options_leaves_the_choice_alone() -> None:
    """Several matches is a shortlist, not a decision the app should make."""

    view = build_conversion_view()
    page = cast(StubPage, view.page)
    before = view.target_dropdown.value
    updates_before = page.updates

    type_into(view.target_dropdown, "cubic")
    blur(view.target_dropdown)

    assert view.target_dropdown.value == before
    # The words that were typed are pushed back out of the field by taking the
    # value away and handing it back - one update each.
    assert page.updates == updates_before + 2


def test_a_query_matching_nothing_leaves_the_choice_alone() -> None:
    """Gibberish filters the menu down to nothing; it must not change the unit."""

    view = build_conversion_view()
    before = view.target_dropdown.value

    type_into(view.target_dropdown, "qqqq")
    blur(view.target_dropdown)

    assert view.target_dropdown.value == before


def test_blurring_an_untouched_box_changes_nothing() -> None:
    """Focusing a dropdown and leaving it again is not a query."""

    view = build_conversion_view()
    page = cast(StubPage, view.page)
    before = view.target_dropdown.value
    updates_before = page.updates

    blur(view.target_dropdown)

    assert view.target_dropdown.value == before
    assert page.updates == updates_before


def test_a_settings_box_resolves_its_typed_choice() -> None:
    """The rule is the app's, not the conversion page's: Settings behaves alike."""

    app = build_app()
    app.build_settings_dialog()
    dropdown = app.settings_theme_dropdown

    type_into(dropdown, "midnight")
    blur(dropdown)

    assert dropdown.value == "Midnight"
    assert app.selected_theme == "Midnight"

