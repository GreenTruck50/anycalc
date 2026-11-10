"""The calculator memory: what MRC / M+ / M- do, and where those keys appear.

No app host is needed - ``pytest -k memory`` runs this on its own. The app is
built over the shared page stub in ``tests/stub_page.py`` and the keys are
pressed the way a tap presses them, through ``AnycalcApp.handle_key``.
"""

from decimal import Decimal

import flet as ft

from keypad import MEMORY_ROW, REGULAR_ROWS, VARIABLE_ROW, pad_keys, pad_rows
from stub_page import build_app, switch_event
from ui import AnycalcApp


def pad_labels(app: AnycalcApp) -> set[str]:
    """Every key label the pad on screen currently carries."""

    labels: set[str] = set()
    for row in app.keypad.controls:
        assert isinstance(row, ft.Row)
        for key in row.controls:
            labels.add(str(key.key).removeprefix("key-"))
    return labels


def type_digits(app: AnycalcApp, keys: str) -> None:
    """Press a run of single-character keys the way a tap does."""

    for key in keys:
        app.handle_key(key)


# --- where the memory keys appear --------------------------------------------


def test_the_pad_rows_put_the_memory_row_above_the_regular_rows() -> None:
    rows = pad_rows(scientific=False)

    assert rows[0] == MEMORY_ROW
    assert rows[1:] == REGULAR_ROWS


def test_the_regular_pad_always_carries_the_memory_keys() -> None:
    app = build_app()

    assert set(MEMORY_ROW) <= pad_labels(app)


def test_the_scientific_pad_carries_them_only_while_the_setting_asks() -> None:
    app = build_app()
    app.set_mode(1)

    assert not set(MEMORY_ROW) & pad_labels(app)

    app.memory_keys_on_scientific = True
    app.rebuild_keypad()

    assert set(MEMORY_ROW) <= pad_labels(app)


def test_the_settings_switch_applies_the_memory_keys_and_saves_them() -> None:
    app = build_app()
    app.set_mode(1)

    app.update_memory_keys_setting(switch_event(True))

    assert app.memory_keys_on_scientific is True
    assert set(MEMORY_ROW) <= pad_labels(app)
    assert "save_data" in app.page.tasks  # type: ignore[attr-defined]


def test_the_settings_dialog_offers_the_memory_keys_switch() -> None:
    app = build_app()
    dialog = app.build_settings_dialog()

    assert dialog.key == "settings-dialog"
    assert app.settings_memory_switch in app.settings_content.controls
    assert app.settings_memory_switch.value is False


def test_the_keyboard_gate_follows_the_memory_setting() -> None:
    """The keyboard reads the same rows the pad is built from."""

    assert "M+" in pad_keys(scientific=True, memory_keys=True)
    assert "M+" not in pad_keys(scientific=True, memory_keys=False)


def test_the_memory_row_carries_the_memory_clear_key() -> None:
    assert MEMORY_ROW == ("MRC", "M+", "M-", "MCLR")


def test_the_memory_keys_take_the_variable_row_off_the_scientific_pad() -> None:
    """One row, two uses: the memory keys replace the variable keys."""

    app = build_app()
    app.set_mode(1)

    assert set(VARIABLE_ROW) <= pad_labels(app)
    assert not set(MEMORY_ROW) & pad_labels(app)

    app.memory_keys_on_scientific = True
    app.rebuild_keypad()

    labels = pad_labels(app)
    assert set(MEMORY_ROW) <= labels
    assert not set(VARIABLE_ROW) & labels


def test_the_scientific_pad_is_the_same_height_with_or_without_the_memory_keys() -> None:
    """Replacing a row rather than adding one is the whole point of the swap."""

    without = pad_rows(scientific=True, memory_keys=False)
    with_memory = pad_rows(scientific=True, memory_keys=True)

    assert len(without) == len(with_memory)
    assert VARIABLE_ROW in without
    assert MEMORY_ROW in with_memory
    assert [row for row in without if row != VARIABLE_ROW] == [
        row for row in with_memory if row != MEMORY_ROW
    ]


def test_the_regular_pad_carries_mclr_without_any_variable_key() -> None:
    """The regular pad has no variables, so its shared row is always memory."""

    app = build_app()

    assert "MCLR" in pad_labels(app)
    assert not set(VARIABLE_ROW) & pad_labels(app)


# --- what the keys do --------------------------------------------------------


def test_m_plus_stores_the_number_on_the_display() -> None:
    app = build_app()
    type_digits(app, "123")

    app.handle_key("M+")

    assert app.memory == Decimal("123")
    assert app.memory_status.visible


def test_m_plus_adds_and_m_minus_subtracts() -> None:
    app = build_app()
    type_digits(app, "100")
    app.handle_key("M+")
    app.handle_key("AC")
    type_digits(app, "40")
    app.handle_key("M-")

    assert app.memory == Decimal("60")


def test_m_plus_works_on_a_live_expression() -> None:
    app = build_app()
    type_digits(app, "2+3")

    app.handle_key("M+")

    assert app.memory == Decimal("5")


def test_an_expression_that_has_no_value_stores_nothing() -> None:
    app = build_app()
    type_digits(app, "2+")

    app.handle_key("M+")

    assert app.memory is None
    assert not app.memory_status.visible


def test_mrc_puts_the_stored_number_into_the_expression() -> None:
    app = build_app()
    type_digits(app, "123")
    app.handle_key("M+")
    app.handle_key("AC")

    app.handle_key("MRC")

    assert app.expression == "123"


def test_pressing_mrc_again_right_after_a_recall_clears_the_memory() -> None:
    app = build_app()
    type_digits(app, "123")
    app.handle_key("M+")
    app.handle_key("MRC")

    app.handle_key("MRC")

    assert app.memory is None
    assert not app.memory_status.visible


def test_any_other_key_between_two_mrc_presses_recalls_again() -> None:
    app = build_app()
    type_digits(app, "123")
    app.handle_key("M+")
    app.handle_key("MRC")
    app.handle_key("AC")

    app.handle_key("MRC")

    assert app.expression == "123"
    assert app.memory == Decimal("123")


def test_mrc_of_an_empty_memory_presses_nothing() -> None:
    app = build_app()
    type_digits(app, "5+")

    app.handle_key("MRC")

    assert app.expression == "5+"


def test_a_negative_memory_comes_back_negative() -> None:
    app = build_app()
    type_digits(app, "5")
    app.handle_key("M-")
    app.handle_key("AC")

    app.handle_key("MRC")

    assert app.memory == Decimal("-5")
    assert app.expression == "-5"


def test_the_memory_survives_clear_and_a_new_expression() -> None:
    app = build_app()
    type_digits(app, "7")
    app.handle_key("M+")
    app.handle_key("AC")
    type_digits(app, "9*9")

    assert app.memory == Decimal("7")

    # MRC puts the number in where the caret is, exactly like typing it there.
    app.handle_key("MRC")

    assert app.expression == "9*97"


def test_the_memory_indicator_stays_hidden_until_something_is_stored() -> None:
    app = build_app()

    assert not app.memory_status.visible


def test_the_memory_indicator_shows_the_stored_number() -> None:
    """The memory is listed the way the variables are: "M = 42"."""

    app = build_app()
    type_digits(app, "42")
    app.handle_key("M+")

    assert app.memory_status.visible
    assert app.memory_status.value == "M = 42"


def test_the_memory_indicator_goes_when_mclr_clears_the_memory() -> None:
    app = build_app()
    type_digits(app, "42")
    app.handle_key("M+")
    app.handle_key("MCLR")

    assert app.memory is None
    assert app.memory_status.value == ""
    assert not app.memory_status.visible


def test_mclr_empties_the_memory_and_leaves_the_expression_alone() -> None:
    """A memory-clear key takes the stored number and nothing else."""

    app = build_app()
    type_digits(app, "123")
    app.handle_key("M+")
    type_digits(app, "+7")
    app.handle_key("MCLR")

    assert app.memory is None
    assert app.expression == "123+7"


def test_mclr_works_on_the_scientific_pad_that_replaced_the_variable_keys() -> None:
    app = build_app()
    app.set_mode(1)
    app.update_memory_keys_setting(switch_event(True))
    type_digits(app, "8")
    app.handle_key("M+")
    app.handle_key("MCLR")

    assert app.memory is None


def test_pressing_m_plus_twice_adds_the_same_number_again() -> None:
    """Like a real calculator: the number the display rests on is re-added."""

    app = build_app()
    type_digits(app, "10")
    app.handle_key("M+")
    app.handle_key("M+")

    assert app.memory == Decimal("20")


def test_m_plus_then_m_minus_of_the_same_number_empties_the_memory() -> None:
    app = build_app()
    type_digits(app, "17")
    app.handle_key("M+")
    app.handle_key("M-")

    assert app.memory == Decimal(0)
    assert not app.memory_status.visible
