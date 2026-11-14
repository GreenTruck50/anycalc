"""Named variables: the Clear Variables key, memory mode, and the save.

No app host is needed - ``pytest -k variables`` runs this on its own. The app is
built over the shared page stub in ``tests/stub_page.py``; the variable dialogs
themselves are exercised by the integration tests in ``tests/test_app.py``.
"""

import json
import types
from decimal import Decimal
from typing import cast

import flet as ft

from config import ERROR_VARIABLES_DISABLED
from data_storage import decode_state, encode_state
from keypad import VARIABLE_ROW
from precision import DEFAULT_PRECISION_DIGITS, set_engine_precision
from stub_page import build_app, fire, switch_event
from ui import AnycalcApp
from variable_dialogs import open_set_variable_dialog


def set_variable(app: AnycalcApp, name: str, value: str) -> None:
    """Give a variable a value the way the Set Variable dialog does."""

    app.variables[name] = Decimal(value)
    app.refresh_variable_status()


def scientific_pad(app: AnycalcApp, memory_keys: bool) -> None:
    """Switch to the Scientific Calculator with the memory keys on or off."""

    app.set_mode(1)
    app.update_memory_keys_setting(switch_event(memory_keys))


def type_keys(app: AnycalcApp, keys: str) -> None:
    """Press a run of keys the way a tap presses them."""

    for key in keys:
        app.handle_key(key)


# --- the Clear Variables key ---------------------------------------------------


def test_the_variable_row_carries_a_clear_variables_key() -> None:
    assert VARIABLE_ROW == ("Set Variable", "Insert Variable", "Clear Variables")

    app = build_app()
    app.set_mode(1)

    assert "Clear Variables" in {
        str(key.key).removeprefix("key-")
        for row in app.keypad.controls
        for key in row.controls  # type: ignore[attr-defined]
    }


def test_clear_variables_empties_every_variable_and_their_line() -> None:
    app = build_app()
    app.set_mode(1)
    set_variable(app, "x", "3")
    set_variable(app, "F", "12")

    assert app.variable_status.visible

    app.handle_key("Clear Variables")

    assert app.variables == {}
    assert app.variable_status.value == ""
    assert not app.variable_status.visible


def test_clear_variables_leaves_the_expression_and_the_memory_alone() -> None:
    app = build_app()
    app.set_mode(1)
    set_variable(app, "x", "4")
    type_keys(app, "2+x")
    app.handle_key("M+")

    app.handle_key("Clear Variables")

    assert app.expression == "2+x"
    assert app.memory == Decimal("6")


# --- variables while the variable keys are on the pad --------------------------


def test_a_variable_is_used_while_the_variable_keys_are_on_the_pad() -> None:
    app = build_app()
    scientific_pad(app, memory_keys=False)
    set_variable(app, "x", "4")

    type_keys(app, "2*x")
    app.handle_key("=")

    assert app.expression == "8"


# --- memory mode: the memory keys hold the pad, the variables do not -----------


def test_memory_mode_reports_a_variable_instead_of_using_it() -> None:
    app = build_app()
    scientific_pad(app, memory_keys=True)
    set_variable(app, "x", "4")

    type_keys(app, "2*x")
    app.handle_key("=")

    assert app.expression == ERROR_VARIABLES_DISABLED
    assert app.result_mode is True


def test_memory_mode_hides_the_variable_line_and_the_live_answer() -> None:
    app = build_app()
    set_variable(app, "x", "4")
    app.set_mode(1)
    assert app.variable_status.visible

    app.update_memory_keys_setting(switch_event(True))

    assert app.memory_mode is True
    assert app.variables_enabled is False
    assert not app.variable_status.visible

    app.expression = "2*x"
    assert app.preview_answer() == ""


def test_memory_mode_gives_the_memory_keys_no_number_from_a_variable() -> None:
    """M+ on an expression the pad will not evaluate stores nothing."""

    app = build_app()
    scientific_pad(app, memory_keys=True)
    set_variable(app, "x", "4")
    app.expression = "2*x"

    app.handle_key("M+")

    assert app.memory is None


def test_the_variables_survive_memory_mode_and_work_again_without_it() -> None:
    app = build_app()
    scientific_pad(app, memory_keys=True)
    set_variable(app, "x", "4")
    app.expression = "2*x"

    assert app.preview_answer() == ""

    # Only the switch is touched here - changing calculator would empty the display.
    app.update_memory_keys_setting(switch_event(False))

    assert app.variables == {"x": Decimal("4")}
    assert app.variable_status.visible
    assert app.preview_answer() == "8"


def test_leaving_memory_mode_clears_the_memory_and_keeps_the_variables() -> None:
    """The swap is one-way for the memory and the other way for the variables."""

    app = build_app()
    scientific_pad(app, memory_keys=True)
    set_variable(app, "x", "4")
    type_keys(app, "8")
    app.handle_key("M+")

    assert app.memory == Decimal("8")

    app.update_memory_keys_setting(switch_event(False))

    assert app.memory is None
    assert not app.memory_status.visible
    assert app.variables == {"x": Decimal("4")}
    assert app.variable_status.visible


def test_the_regular_pad_never_reports_the_memory_mode_error() -> None:
    """A name on the regular pad is not arithmetic - that stays the engine's call."""

    app = build_app()
    set_variable(app, "x", "4")
    app.expression = "2*x"

    try:
        app.evaluate("2*x")
    except ValueError as error:
        assert str(error) != ERROR_VARIABLES_DISABLED
    else:
        raise AssertionError("the regular pad read a name it should not read")


# --- the variables come back with the saved app data --------------------------


def saved_state(app: AnycalcApp) -> str:
    """What the app would write to client storage right now."""

    return encode_state(app._state_snapshot())


def test_the_saved_state_carries_the_named_variables() -> None:
    app = build_app()
    app.set_mode(1)
    set_variable(app, "x", "4")
    set_variable(app, "F", "12")

    assert json.loads(saved_state(app))["variables"] == [["x", "4"], ["F", "12"]]


def test_setting_a_variable_through_the_dialog_saves_it() -> None:
    app = build_app()
    app.set_mode(1)

    open_set_variable_dialog(app)
    dialog = cast(ft.AlertDialog, app.page.dialogs[-1])  # type: ignore[attr-defined]
    value_field = cast(ft.TextField, cast(ft.Column, dialog.content).controls[1])
    value_field.value = "42"
    save = cast(ft.TextButton, dialog.actions[1])
    fire(save.on_click, types.SimpleNamespace(control=save))

    assert app.variables == {"x": Decimal("42")}
    assert json.loads(saved_state(app))["variables"] == [["x", "42"]]


def test_named_variables_come_back_into_a_fresh_app() -> None:
    app = build_app()
    app.set_mode(1)
    set_variable(app, "x", "4")
    set_variable(app, "F", "12")

    restored = decode_state(saved_state(app))
    fresh = build_app()
    fresh.restore_variables(restored.variables)

    assert fresh.variables == {"x": Decimal("4"), "F": Decimal("12")}


def test_a_restored_variable_keeps_every_digit_the_engine_computed() -> None:
    """The value is stored as the engine wrote it - at whatever precision the app
    was running at - and nothing shortens it on the way through storage."""

    app = build_app()
    set_engine_precision(50)
    try:
        app.set_mode(1)
        app.expression = "1/3"
        app.handle_key("=")
        app.variables["x"] = Decimal(app.expression)
        assert len(app.expression) > 40  # the engine's precision, not 15 digits

        fresh = build_app()
        fresh.restore_variables(decode_state(saved_state(app)).variables)

        assert fresh.variables["x"] == Decimal(1) / Decimal(3)
    finally:
        set_engine_precision(DEFAULT_PRECISION_DIGITS)


def test_a_restored_variable_is_usable_right_where_it_lands() -> None:
    app = build_app()
    app.set_mode(1)

    app.restore_variables((("x", "4"),))
    app.refresh_variable_status()
    app.expression = "2*x"

    assert app.variable_status.value == "x = 4"
    assert app.variable_status.visible
    assert app.preview_answer() == "8"


def test_a_saved_name_the_app_no_longer_offers_is_dropped() -> None:
    app = build_app()

    app.restore_variables((("Ω", "5"), ("x", "4")))

    assert app.variables == {"x": Decimal("4")}


def test_a_saved_value_that_is_not_a_finite_number_is_dropped() -> None:
    app = build_app()

    app.restore_variables(
        (("x", "banana"), ("y", "NaN"), ("z", "Infinity"), ("q", "7"))
    )

    assert app.variables == {"q": Decimal("7")}


def test_clearing_the_variables_empties_the_saved_state_too() -> None:
    app = build_app()
    app.set_mode(1)
    set_variable(app, "x", "3")
    assert json.loads(saved_state(app))["variables"] == [["x", "3"]]

    app.handle_key("Clear Variables")

    assert json.loads(saved_state(app))["variables"] == []
    assert "save_data" in app.page.tasks  # type: ignore[attr-defined]
