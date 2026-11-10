"""The two calculator pads: which keys they show and how a key looks.

The regular rows are the keypad; the scientific pad only adds its extra rows on
top of them, which is why every key - ``(``, ``)``, ``%``, ``±`` - is defined
exactly once and a test can keep asserting there is exactly one of each.

A key here only wires its click to ``on_key``; what a press means to the
expression is the app's business (``src/ui.py``), and the two variable-dialog
keys are just labels the app dispatches on.
"""

from typing import Callable

import flet as ft

import styles

# The utility keys share one row rather than adding a row of their own, so the
# pad stays as tall as it was in either mode.
REGULAR_ROWS = (
    ("AC", "⌫", "(", ")", "±", "%"),
    ("7", "8", "9", "÷"),
    ("4", "5", "6", "×"),
    ("1", "2", "3", "−"),
    ("0", ".", "=", "+"),
)

# The scientific rows add only what the regular rows lack: ( ) % ± already live in
# the utility row below, which is why "^" joins this row rather than repeating a
# fourth row of keys the pad already has. The row that used to hold the variable
# keys is assembled by pad_rows() instead, because the memory keys share that slot.
SCIENTIFIC_ROWS = (
    ("sin", "cos", "tan", "√"),
    ("log", "ln", "𝜋", "e", "^"),
)

SCIENTIFIC_KEYS = frozenset(key for row in SCIENTIFIC_ROWS for key in row)

# The two variable keys open dialogs instead of editing the expression.
DIALOG_KEYS = ("Set Variable", "Insert Variable")

# The memory and the named variables share one row of the pad. MRC puts what is
# stored into the expression and clears it when pressed again right after; M+ and
# M- fold the number the display rests on into it; MCLR empties the memory
# outright, the way a physical calculator's memory-clear key does. The Regular
# Calculator always carries this row - it has no variables to make room for - and
# the Scientific Calculator carries it instead of the variable row while the
# setting that asks for memory keys there is on.
MEMORY_ROW = ("MRC", "M+", "M-", "MCLR")
MEMORY_CLEAR_KEY = "MCLR"

# The same slot when the memory keys are not wanted: the two variable dialogs and
# a key that empties every variable the pad has set.
VARIABLE_ROW = ("Set Variable", "Insert Variable", "Clear Variables")
CLEAR_VARIABLES_KEY = "Clear Variables"


def key_color(label: str) -> str:
    """The background a key gets for its label, on either pad.

    The scientific keys and the shared memory / variable row carry the operator
    color because on both pads they are the band of controls above the digits;
    "=" is the accent and the two clearing keys are the danger color wherever
    they appear.
    """

    if label == "=":
        return styles.ACCENT
    if label in ("AC", "⌫"):
        return styles.KEY_DANGER
    if label in ("÷", "×", "−", "+", "%", "±"):
        return styles.KEY_OPERATOR
    if label in MEMORY_ROW or label in VARIABLE_ROW or label in SCIENTIFIC_KEYS:
        return styles.KEY_OPERATOR
    return styles.KEY_DEFAULT


def make_key(
    label: str,
    on_key: Callable[[str], None],
    color: str | None = None,
    text_color: str | None = None,
) -> ft.Container:
    """One key of the pad: a fixed-size tappable tile labelled ``label``.

    A bare ``Container`` tap target has no press feedback of its own, which is
    what makes the pad look dead next to the header's Material buttons - ``ink``
    is what puts the same ripple inside the tile, coloured by ``KEY_INK`` so it
    reads on both the dark keys and the accent ``=``.

    The ``key`` is ``key-<label>`` on purpose - the integration tests in
    ``tests/test_app.py`` address the keypad through it.
    """

    def handle_click(e):
        del e
        on_key(label)

    return ft.Container(
        key=f"key-{label}",
        content=ft.Text(
            label,
            size=14 if len(label) > 8 else 19,
            color=text_color or styles.TEXT_PRIMARY,
            text_align=ft.TextAlign.CENTER,
        ),
        bgcolor=color or styles.KEY_DEFAULT,
        border_radius=14,
        alignment=ft.Alignment.CENTER,
        expand=True,
        height=54,
        ink=True,
        ink_color=styles.KEY_INK,
        on_click=handle_click,
    )

# A physical keyboard presses this very pad, so this says which pad key a real
# key stands for. pad_key() below then refuses anything the pad on screen does
# not carry, which is how "^", "e" and "√" stay scientific-mode keys without a
# second rule anywhere else. Flutter reports printable keys as their character -
# letters upper-case, so both spellings of "e" are listed - and the editing keys
# by name.
KEYBOARD_KEYS = {
    **{digit: digit for digit in "0123456789"},
    "+": "+",
    "-": "−",
    "_": "−",
    "*": "×",
    "/": "÷",
    "^": "^",
    "(": "(",
    ")": ")",
    "%": "%",
    ".": ".",
    ",": ".",
    "=": "=",
    "±": "±",
    "√": "√",
    "𝜋": "𝜋",
    "e": "e",
    "E": "e",
    "Enter": "=",
    "Numpad Enter": "=",
    "Backspace": "⌫",
    "Delete": "AC",
    "Escape": "AC",
}


def pad_rows(scientific: bool, memory_keys: bool = True) -> tuple[tuple[str, ...], ...]:
    """The rows the pad on screen shows, top to bottom.

    This is the one place that knows how a pad is assembled: the scientific rows
    only in scientific mode, the regular rows - which both pads carry - last, and
    between them one shared slot that holds the memory row or the variable row.
    The memory keys replace the variable keys rather than being added beside them,
    so the scientific pad is the same height with the setting on or off, and the
    regular pad - which has no variables at all - always shows the memory row.
    The pad is built from this, and so is the keyboard gate, which is why a key
    can never mean a key that is not on the screen.
    """

    rows: list[tuple[str, ...]] = []
    if scientific:
        rows.extend(SCIENTIFIC_ROWS)
        rows.append(MEMORY_ROW if memory_keys else VARIABLE_ROW)
    else:
        rows.append(MEMORY_ROW)
    rows.extend(REGULAR_ROWS)
    return tuple(rows)


def pad_keys(scientific: bool, memory_keys: bool = True) -> frozenset[str]:
    """Every key the pad on screen actually shows."""

    return frozenset(key for row in pad_rows(scientific, memory_keys) for key in row)


def pad_key(key: str, scientific: bool, memory_keys: bool = True) -> str | None:
    """The pad key a physical key stands for, or None if this pad has no such key.

    Unmapped keys (letters the pad does not carry, arrows, Tab, modifiers) and keys
    whose pad key only the other mode shows both come back as None, so the caller
    has one rule to honour: press what comes back, or press nothing.
    """

    label = KEYBOARD_KEYS.get(key)
    return label if label in pad_keys(scientific, memory_keys) else None

