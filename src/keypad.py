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

from styles import (
    ACCENT,
    KEY_DANGER,
    KEY_DEFAULT,
    KEY_INK,
    KEY_OPERATOR,
    TEXT_PRIMARY,
)

# The utility keys share one row rather than adding a row of their own, so the
# pad stays as tall as it was in either mode.
REGULAR_ROWS = (
    ("AC", "⌫", "(", ")", "±", "%"),
    ("7", "8", "9", "÷"),
    ("4", "5", "6", "×"),
    ("1", "2", "3", "−"),
    ("0", ".", "=", "+"),
)

# The regular rows are part of the scientific pad too, so these rows add only
# what those lack: ( ) % ± already live in the utility row below, which is why
# "^" joins this row rather than repeating a fourth row of keys the pad already
# has.
SCIENTIFIC_ROWS = (
    ("sin", "cos", "tan", "√"),
    ("log", "ln", "π", "e", "^"),
    ("Set Variable", "Insert Variable"),
)

# The two variable keys open dialogs instead of editing the expression.
DIALOG_KEYS = ("Set Variable", "Insert Variable")


def key_color(label: str) -> str:
    """The background a regular-pad key gets for its label."""

    if label == "=":
        return ACCENT
    if label in ("AC", "⌫"):
        return KEY_DANGER
    if label in ("÷", "×", "−", "+", "%", "±"):
        return KEY_OPERATOR
    return KEY_DEFAULT


def make_key(
    label: str,
    on_key: Callable[[str], None],
    color: str = KEY_DEFAULT,
    text_color: str = TEXT_PRIMARY,
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
            color=text_color,
            text_align=ft.TextAlign.CENTER,
        ),
        bgcolor=color,
        border_radius=14,
        alignment=ft.Alignment.CENTER,
        expand=True,
        height=54,
        ink=True,
        ink_color=KEY_INK,
        on_click=handle_click,
    )
