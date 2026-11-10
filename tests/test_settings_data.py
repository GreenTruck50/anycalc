"""How much history the app keeps, and how all of it can be thrown away.

No app host is needed - ``pytest -k settings_data`` runs this on its own. The app
is built over the shared page stub in ``tests/stub_page.py``, and the settings
controls are fired the way the page fires them.
"""

import math
import types
from decimal import Decimal
from typing import Any

import pytest

import pi
import styles
from config import DEFAULT_HISTORY_LENGTH, MAX_HISTORY_ITEMS
from precision import Precision
from stub_page import build_app, fire, switch_event


@pytest.fixture(autouse=True)
def _leave_the_live_theme_as_found():
    """Put back the palette an app started here replaced."""

    before = styles.get_active_theme()
    try:
        yield
    finally:
        styles.set_active_theme(before.name)


def find_settings_control(app, key: str) -> Any:
    """One control inside the settings dialog, found by its key.

    The walk follows both child lists (``controls``) and single children
    (``content``), since a wrapper like ``Semantics`` or ``Container`` hangs its
    child off the latter.
    """

    stack = list(app.settings_content.controls)
    while stack:
        control = stack.pop()
        if getattr(control, "key", None) == key:
            return control
        children = getattr(control, "controls", None)
        if children:
            stack.extend(children)
        single = getattr(control, "content", None)
        if single is not None:
            stack.append(single)
    raise AssertionError(f"the settings dialog has no control keyed {key!r}")


def fill_history(app, count: int) -> None:
    """Stand in for ``count`` finished calculations, oldest first."""

    app.history = [(f"{index}+1", str(index + 1)) for index in range(count)]


def tap(handler) -> None:
    """Fire a control's handler the way the page does: with an event."""

    fire(handler, types.SimpleNamespace(control=None))


def reset_prompt(app):
    """The confirmation dialog the reset button put up, if it did."""

    prompts = [
        dialog
        for dialog in app.page.dialogs  # type: ignore[attr-defined]
        if getattr(dialog, "key", None) == "reset-confirmation-dialog"
    ]
    assert len(prompts) == 1, "the reset button showed no confirmation"
    return prompts[0]


def test_the_settings_dialog_offers_the_history_length_and_two_actions() -> None:
    app = build_app()
    app.build_settings_dialog()

    dropdown = find_settings_control(app, "settings-history-length")
    assert [option.key for option in dropdown.options] == ["10", "25", "50", "100"]
    assert dropdown.value == str(DEFAULT_HISTORY_LENGTH)

    assert find_settings_control(app, "settings-clear-history") is not None
    assert find_settings_control(app, "settings-reset-all-data") is not None


def test_shortening_the_history_drops_the_oldest_entries_at_once() -> None:
    app = build_app()
    app.build_settings_dialog()
    fill_history(app, 30)

    find_settings_control(app, "settings-history-length").value = "10"
    app.update_history_length(None)

    assert app.history_limit == 10
    assert app.history == [(f"{index}+1", str(index + 1)) for index in range(20, 30)]
    assert "save_data" in app.page.tasks  # type: ignore[attr-defined]


def test_the_history_limit_is_saved_and_capped() -> None:
    app = build_app()
    app.build_settings_dialog()

    find_settings_control(app, "settings-history-length").value = "1000"
    app.update_history_length(None)

    assert app.history_limit == MAX_HISTORY_ITEMS
    assert app._state_snapshot().history_limit == MAX_HISTORY_ITEMS


def test_a_finished_calculation_never_grows_past_the_limit() -> None:
    app = build_app()
    app.build_settings_dialog()
    find_settings_control(app, "settings-history-length").value = "10"
    app.update_history_length(None)
    fill_history(app, 10)

    for _ in range(4):
        app.handle_key("1")
        app.handle_key("+")
        app.handle_key("1")
        app.handle_key("=")

    assert len(app.history) == 10
    assert app.history[-1] == ("1+1", "2")


def test_the_clear_history_button_empties_the_history() -> None:
    app = build_app()
    app.build_settings_dialog()
    fill_history(app, 5)

    tap(find_settings_control(app, "settings-clear-history").on_click)

    assert app.history == []


def test_resetting_asks_first_and_cancel_changes_nothing() -> None:
    app = build_app()
    app.build_settings_dialog()
    fill_history(app, 3)

    tap(find_settings_control(app, "settings-reset-all-data").on_click)
    prompt = reset_prompt(app)
    assert [button.content for button in prompt.actions] == ["Cancel", "Reset"]

    tap(prompt.actions[0].on_click)

    assert len(app.history) == 3
    assert app.page.popped == 1  # type: ignore[attr-defined]


def test_reset_throws_everything_away_and_restores_the_defaults() -> None:
    app = build_app()
    app.build_settings_dialog()
    fill_history(app, 4)
    app.variables["x"] = Decimal("7")
    app.handle_key("8")
    app.handle_key("M+")
    app.set_mode(1)
    app.update_memory_keys_setting(switch_event(True))
    app.settings_precision_decimals.value = "4"
    app.update_precision(None)
    app.apply_theme("Light")
    pi.set_program_pi(Decimal("3.14159"), 5, decimals="14159")

    tap(find_settings_control(app, "settings-reset-all-data").on_click)
    tap(reset_prompt(app).actions[1].on_click)

    assert app.history == []
    assert app.variables == {}
    assert app.memory is None
    assert not app.memory_status.visible
    assert app.memory_keys_on_scientific is False
    assert app.precision == Precision()
    assert app.history_limit == DEFAULT_HISTORY_LENGTH
    assert app.selected_theme == styles.DEFAULT_THEME.name
    assert pi.program_pi() == Decimal(str(math.pi))
    assert "store_reset_data" in app.page.tasks  # type: ignore[attr-defined]


def test_the_reset_leaves_the_open_settings_dialog_showing_the_defaults() -> None:
    app = build_app()
    app.build_settings_dialog()
    find_settings_control(app, "settings-history-length").value = "10"
    app.update_history_length(None)
    app.settings_precision_decimals.value = "4"
    app.update_precision(None)
    app.update_memory_keys_setting(switch_event(True))

    app.reset_app_data()

    assert app.settings_history_length.value == str(DEFAULT_HISTORY_LENGTH)
    assert app.settings_precision_decimals.value == "auto"
    assert app.settings_precision_rounding.value == "half-up"
    assert app.settings_memory_switch.value is False
    assert app.settings_theme_dropdown.value == styles.DEFAULT_THEME.name


def test_the_reset_forgets_the_saved_pi_and_writes_the_empty_state_back() -> None:
    app = build_app()
    app.build_settings_dialog()
    pi.set_program_pi(Decimal("3.14159"), 5, decimals="14159")

    app.reset_app_data()
    snapshot = app._state_snapshot(include_pi=True)
    fallback_decimals = str(math.pi).partition(".")[2]

    assert snapshot.pi_digits == len(fallback_decimals)
    assert snapshot.pi_text == f"3.{fallback_decimals}"
