"""The physical keyboard: what a real key does to the calculator pad.

No app host is needed - ``pytest -k keyboard`` runs this on its own. The key
mapping is a pure function in ``keypad.py``, and the gates around it are driven
here with the same ``ft.KeyboardEvent`` payloads the page hands
``AnycalcApp.handle_keyboard_event``, on an app built over a stub page (the
pattern ``tests/test_pi_view.py`` uses for a view).
"""

import inspect
import types
from collections.abc import Generator
from typing import cast

import flet as ft
import pytest

import pi
from keypad import KEYBOARD_KEYS, pad_key, pad_keys
from ui import AnycalcApp
from variable_dialogs import open_set_variable_dialog


@pytest.fixture(autouse=True)
def _leave_the_program_pi_as_found() -> Generator[None, None, None]:
    """Put back the process-wide pi that building the app replaces.

    ``AnycalcApp`` installs its own computed pi on startup, exactly as it does in
    a real window, and that value is process-wide state - the pi-engine tests
    assert on the fallback pi, so they must not see this app's. Same guard
    ``tests/test_pi_view.py`` runs its fixture with.
    """

    before = (pi.program_pi(), pi.program_pi_digits(), pi.program_pi_decimals())
    try:
        yield
    finally:
        pi.set_program_pi(before[0], before[1], decimals=before[2])


class StubPage:
    """Just enough of a page for ``AnycalcApp.build()``: it updates and runs tasks."""

    def __init__(self) -> None:
        self.width: int | float | None = 400
        self.height: int | float | None = 780
        self.window = types.SimpleNamespace(
            width=None, height=None, min_width=None, min_height=None
        )
        self.updates = 0
        self.tasks: list[str] = []
        self.dialogs: list[object] = []
        self.popped = 0

    def update(self, *_controls: ft.Control) -> None:
        del _controls
        self.updates += 1

    def add(self, *_controls: ft.Control) -> None:
        del _controls

    def run_task(self, handler, *args) -> None:
        """Stand in for ``Page.run_task``: there is no event loop here, so the
        coroutine is closed rather than awaited - the test only cares that the
        page was asked to schedule it."""

        self.tasks.append(getattr(handler, "__name__", str(handler)))
        result = handler(*args)
        if inspect.iscoroutine(result):
            result.close()

    def show_dialog(self, dialog: ft.AlertDialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        self.popped += 1


def key_event(key: str, **modifiers: bool) -> ft.KeyboardEvent:
    """The payload ``page.on_keyboard_event`` hands the app for one key press."""

    return ft.KeyboardEvent(
        name="keyboard_event",
        control=cast(ft.Page, None),
        key=key,
        shift=modifiers.get("shift", False),
        ctrl=modifiers.get("ctrl", False),
        alt=modifiers.get("alt", False),
        meta=modifiers.get("meta", False),
    )


def build_app() -> AnycalcApp:
    """The whole app over a stub page, opening on the regular pad."""

    app = AnycalcApp(cast(ft.Page, StubPage()))
    app.build()
    return app


def type_keys(app: AnycalcApp, keys: str) -> None:
    """Press a run of keys the way the page would deliver them."""

    for key in keys:
        app.handle_keyboard_event(key_event(key))


def fire(handler: object, event: object | None = None) -> None:
    """Call a control's own handler the way the page calls it.

    A Flet handler takes the event, except the ones written as a bare lambda that
    ignores it - like the dialog buttons' ``on_click`` - and those are called with
    nothing at all.
    """

    assert callable(handler), "the control carries no handler to call"
    if event is None:
        handler()
    else:
        handler(event)


# --- the mapping, with no app in sight ---------------------------------------


def test_every_mapped_key_is_a_key_the_pad_actually_has() -> None:
    """No mapping may invent a key: every label it hands back is on a pad.

    The scientific pad shows the regular rows underneath its own, so it is the
    superset every label has to appear in.
    """

    available = pad_keys(scientific=True)
    for key, label in KEYBOARD_KEYS.items():
        assert label in available, f"{key!r} maps to {label!r}, which no pad shows"


def test_digits_and_operators_map_to_their_pad_keys() -> None:
    for digit in "0123456789":
        assert pad_key(digit, scientific=False) == digit

    assert pad_key("+", scientific=False) == "+"
    assert pad_key("-", scientific=False) == "−"
    assert pad_key("_", scientific=False) == "−"
    assert pad_key("*", scientific=False) == "×"
    assert pad_key("/", scientific=False) == "÷"
    assert pad_key(".", scientific=False) == "."
    assert pad_key(",", scientific=False) == "."
    assert pad_key("(", scientific=False) == "("
    assert pad_key(")", scientific=False) == ")"
    assert pad_key("%", scientific=False) == "%"


def test_the_editing_keys_map_to_the_utility_row() -> None:
    assert pad_key("Enter", scientific=False) == "="
    assert pad_key("Numpad Enter", scientific=False) == "="
    assert pad_key("=", scientific=False) == "="
    assert pad_key("Backspace", scientific=False) == "⌫"
    assert pad_key("Escape", scientific=False) == "AC"
    assert pad_key("Delete", scientific=False) == "AC"


def test_scientific_only_keys_are_refused_on_the_regular_pad() -> None:
    for key in ("^", "e", "E", "√"):
        assert pad_key(key, scientific=False) is None
        assert pad_key(key, scientific=True) in {"^", "e", "√"}


def test_keys_the_pad_has_no_answer_for_are_refused() -> None:
    for key in ("a", "A", "s", "ArrowUp", "Tab", "Space", "F1", ""):
        assert pad_key(key, scientific=False) is None
        assert pad_key(key, scientific=True) is None

# --- the app in front of the mapping ----------------------------------------


def test_typing_on_the_keyboard_builds_and_commits_an_expression() -> None:
    app = build_app()

    type_keys(app, "2+3")
    assert app.expression == "2+3"

    app.handle_keyboard_event(key_event("Enter"))
    assert app.expression == "5"
    assert app.result_mode is True
    assert app.display.value == "5"
    assert app.expression_label.value == "RESULT"


def test_escape_clears_and_backspace_edits() -> None:
    app = build_app()

    type_keys(app, "12*")
    app.handle_keyboard_event(key_event("Backspace"))
    assert app.expression == "12"

    app.handle_keyboard_event(key_event("Escape"))
    assert app.expression == ""
    assert app.display.value == "0"


def test_a_modifier_hands_the_key_back_to_the_system() -> None:
    app = build_app()

    for event in (
        key_event("5", ctrl=True),
        key_event("5", alt=True),
        key_event("5", meta=True),
    ):
        app.handle_keyboard_event(event)

    assert app.expression == ""


def test_a_key_press_while_the_caret_is_in_a_field_does_not_double_up() -> None:
    """The display types its own keys, so the pad must not press them again."""

    app = build_app()
    app.handle_keyboard_event(key_event("2"))
    assert app.expression == "2"

    fire(app.display.on_focus, types.SimpleNamespace(control=app.display))
    assert app.text_field_focused is True

    app.handle_keyboard_event(key_event("+"))
    assert app.expression == "2"

    fire(app.display.on_blur, types.SimpleNamespace(control=app.display))
    assert app.text_field_focused is False
    app.handle_keyboard_event(key_event("+"))
    assert app.expression == "2+"


def test_focusing_the_display_still_selects_a_result() -> None:
    """Wrapping the field's focus must not drop the handler that was on it."""

    app = build_app()
    type_keys(app, "2+2")
    app.handle_keyboard_event(key_event("Enter"))
    assert app.result_mode is True

    fire(app.display.on_focus, types.SimpleNamespace(control=app.display))

    assert app.display.selection == ft.TextSelection(0, len("4"))


def test_enter_in_the_display_commits_the_expression() -> None:
    """The field owns Enter, so the app commits through its submit handler."""

    app = build_app()
    app.handle_display_change("6*7")

    fire(app.display.on_submit, types.SimpleNamespace(control=app.display))

    assert app.expression == "42"
    assert app.result_mode is True


def test_the_regular_pad_refuses_a_key_the_scientific_pad_has() -> None:
    app = build_app()

    type_keys(app, "^")
    assert app.expression == ""

    app.set_mode(1)
    assert app.scientific is True
    type_keys(app, "^")
    assert app.expression == "^"


def test_another_page_has_no_pad_to_press() -> None:
    app = build_app()
    app.open_pi()

    assert app.calculator_showing is False
    type_keys(app, "7+1")
    assert app.expression == ""

    app.set_mode(0)
    assert app.calculator_showing is True
    type_keys(app, "7+1")
    assert app.expression == "7+1"


def test_typing_in_the_set_variable_dialog_does_not_edit_the_expression() -> None:
    app = build_app()
    type_keys(app, "12+")
    page = cast(StubPage, app.page)

    open_set_variable_dialog(app)
    dialog = cast(ft.AlertDialog, page.dialogs[-1])
    value_field = cast(ft.TextField, cast(ft.Column, dialog.content).controls[1])

    fire(value_field.on_focus, types.SimpleNamespace(control=value_field))
    assert app.text_field_focused is True

    for key in "3.5":
        app.handle_keyboard_event(key_event(key))
    assert app.expression == "12+"

    cancel = cast(ft.TextButton, cast(list[ft.Control], dialog.actions)[0])
    fire(cancel.on_click)

    assert page.popped == 1
    assert app.text_field_focused is False


def test_the_pages_keyboard_event_is_wired_to_the_app() -> None:
    app = build_app()

    # A bound method is rebuilt on every attribute access, so this compares the
    # handler the page holds against the app's own, not their identity.
    assert app.page.on_keyboard_event == app.handle_keyboard_event


# --- the arrow keys walk the history ----------------------------------------


def test_the_arrow_keys_walk_the_history_back_into_the_display() -> None:
    app = build_app()

    type_keys(app, "1+1")
    app.handle_keyboard_event(key_event("Enter"))
    type_keys(app, "2+2")
    app.handle_keyboard_event(key_event("Enter"))
    assert app.history == [("1+1", "2"), ("2+2", "4")]

    app.handle_keyboard_event(key_event("AC"))

    app.handle_keyboard_event(key_event("ArrowUp"))
    assert app.expression == "2+2"
    app.handle_keyboard_event(key_event("ArrowUp"))
    assert app.expression == "1+1"
    app.handle_keyboard_event(key_event("ArrowUp"))
    assert app.expression == "1+1", "the walk stops at the oldest entry"

    app.handle_keyboard_event(key_event("ArrowDown"))
    assert app.expression == "2+2"
    app.handle_keyboard_event(key_event("ArrowDown"))
    assert app.expression == "", "past the newest entry the display is ready again"


def test_the_history_walk_starts_again_once_the_user_edits() -> None:
    app = build_app()

    type_keys(app, "3+3")
    app.handle_keyboard_event(key_event("Enter"))
    app.handle_keyboard_event(key_event("ArrowUp"))
    assert app.expression == "3+3"

    app.handle_display_change("9")
    app.handle_keyboard_event(key_event("ArrowUp"))
    assert app.expression == "3+3"


def test_the_arrow_keys_do_nothing_while_the_history_is_empty() -> None:
    app = build_app()

    app.handle_keyboard_event(key_event("ArrowUp"))
    app.handle_keyboard_event(key_event("ArrowDown"))

    assert app.expression == ""
    assert app.history_walk is None

