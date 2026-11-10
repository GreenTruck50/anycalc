"""The calculator memory: what MRC / M+ / M- / MCLR do, where those keys appear and
where the stored number is listed.

No app host is needed - ``pytest -k memory`` runs this on its own. The app is
built over the shared page stub in ``tests/stub_page.py`` and the keys are
pressed the way a tap presses them, through ``AnycalcApp.handle_key``.
"""

from decimal import Decimal
from typing import cast

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
    assert app.settings_memory_row in app.settings_content.controls
    assert app.settings_memory_switch in app.settings_memory_row.controls
    assert app.settings_memory_switch.value is False


def test_the_memory_switch_label_wraps_instead_of_being_cut_off() -> None:
    """The one long sentence in the dialog has to be text that can wrap.

    A switch's own label - string or control - is laid out in a row sized to its
    contents, so nothing constrains it and a long sentence is cut off in a narrow
    dialog. The words therefore sit beside the toggle as a sibling that is given
    the width the row has left, which is what lets them break at word boundaries;
    being outside the switch, they carry their own click handler.
    """

    app = build_app()
    app.build_settings_dialog()

    switch = app.settings_memory_switch
    label = app.settings_memory_label

    assert switch.label is None
    assert label in app.settings_memory_row.controls
    assert label.expand
    assert label.on_click is not None
    text = label.content
    assert isinstance(text, ft.Text)
    assert not text.no_wrap
    assert text.value == (
        "Memory keys on the scientific pad (replaces the variable keys)"
    )


def test_clicking_the_label_words_flips_the_memory_keys_setting() -> None:
    """Clicking the words does exactly what clicking the toggle does."""

    app = build_app()
    app.build_settings_dialog()
    app.set_mode(1)

    app.toggle_memory_keys_setting(None)

    assert app.memory_keys_on_scientific is True
    assert app.settings_memory_switch.value is True
    assert set(MEMORY_ROW) <= pad_labels(app)

    app.toggle_memory_keys_setting(None)

    assert app.memory_keys_on_scientific is False
    assert app.settings_memory_switch.value is False
    assert set(VARIABLE_ROW) <= pad_labels(app)


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


# --- the memory goes with the row that carries it ------------------------------


def test_turning_the_memory_keys_off_clears_the_memory_it_has_no_keys_for() -> None:
    """Variable mode takes the memory row back, and the memory with it."""

    app = build_app()
    app.set_mode(1)
    app.update_memory_keys_setting(switch_event(True))
    type_digits(app, "42")
    app.handle_key("M+")

    assert app.memory == Decimal("42")

    app.update_memory_keys_setting(switch_event(False))

    assert app.memory is None
    assert app.memory_status.value == ""
    assert not app.memory_status.visible


def test_the_scientific_pad_clears_a_memory_it_arrives_without_keys_for() -> None:
    app = build_app()
    type_digits(app, "42")
    app.handle_key("M+")

    app.set_mode(1)

    assert app.memory is None
    assert not app.memory_status.visible


def test_the_regular_pad_keeps_the_memory_it_was_given() -> None:
    """The regular pad always carries the memory keys, so nothing is dropped."""

    app = build_app()
    app.set_mode(1)
    app.update_memory_keys_setting(switch_event(True))
    type_digits(app, "42")
    app.handle_key("M+")

    app.set_mode(0)

    assert app.memory == Decimal("42")
    assert app.memory_status.visible


# --- where the memory is listed ------------------------------------------------


def display_lines(app: AnycalcApp) -> list[ft.Control]:
    """The controls under the display: the preview slot and the status lines."""

    panel = cast(ft.Column, app.display_panel.content)
    return list(panel.controls)


def test_the_memory_is_listed_where_the_variables_are() -> None:
    app = build_app()

    lines = display_lines(app)

    assert any(line is app.memory_status for line in lines)
    assert any(line is app.variable_status for line in lines)


def test_only_one_of_the_two_lines_is_on_screen_at_a_time() -> None:
    app = build_app()
    app.set_mode(1)
    app.variables["x"] = Decimal("3")
    app.refresh_variable_status()

    assert app.variable_status.visible
    assert not app.memory_status.visible

    app.update_memory_keys_setting(switch_event(True))
    type_digits(app, "8")
    app.handle_key("M+")

    assert app.memory_status.visible
    assert not app.variable_status.visible
