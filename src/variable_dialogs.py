"""The variable dialogs on the scientific pad: "Set Variable" and "Insert Variable".

Both dialogs are built on request and popped again on the spot, so they keep no
state of their own - the values they read and write are the app's (``app.page``,
``app.variables``, ``app.expression``, ``app.result_mode``), which is also how
they stay in step with the display after the dialog closes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import flet as ft

from calculate import calculate, is_number
from config import VARIABLE_NAMES, VARIABLE_OPTIONS

if TYPE_CHECKING:
    from ui import AnycalcApp


def open_set_variable_dialog(app: AnycalcApp) -> None:
    """Ask for a name and a value, and store it as a named variable.

    The value is not taken literally: it goes through the scientific expression
    engine first, so "2 * pi" or another variable can be assigned as well. While
    the display rests on a result, a third button offers that number directly.
    """
    page = app.page
    variables = app.variables

    name_picker = ft.Dropdown(
        label="Variable",
        value=next(
            (name for name in ("x", "y", "z") if name not in variables),
            "x",
        ),
        options=[
            ft.DropdownOption(
                key=symbol,
                text=f"{symbol} — {label}" if label != symbol else symbol,
            )
            for symbol, label in VARIABLE_OPTIONS
        ],
        enable_search=True,
        expand=True,
    )
    value_field = ft.TextField(
        label="Value",
        value="",
        autofocus=True,
    )

    def assign_variable(value):
        name = name_picker.value
        if name not in VARIABLE_NAMES:
            value_field.error = "Choose a variable name"
            page.update()
            return

        try:
            variables[name] = Decimal(value)
        except InvalidOperation as error:
            value_field.error = f"Invalid number: {error}"
            page.update()
            return

        app.refresh_variable_status()
        app.refresh_preview()
        page.pop_dialog()
        page.update()

    def save_variable(e):
        del e
        if not value_field.value.strip():
            value_field.error = "Enter a value"
            page.update()
            return

        try:
            value = calculate(
                value_field.value,
                scientific=True,
                degrees=app.degrees,
                variables=variables,
            )
            assign_variable(value)
        except (SyntaxError, ValueError, InvalidOperation) as error:
            value_field.error = str(error)
            page.update()
            return

    def use_result_number():
        assign_variable(app.expression)

    actions: list[ft.Control] = [
        ft.TextButton(
            content="Cancel",
            on_click=lambda: page.pop_dialog(),
        ),
        ft.TextButton(
            content="Save",
            on_click=save_variable,
        ),
    ]
    if app.result_mode and is_number(app.expression):
        actions.insert(
            1,
            ft.TextButton(
                content="Use Result Number",
                on_click=use_result_number,
            ),
        )

    page.show_dialog(
        ft.AlertDialog(
            title="Set Variable",
            content=ft.Column(
                [
                    name_picker,
                    value_field,
                ],
                tight=True,
                spacing=12,
                width=320,
            ),
            actions=actions,
        )
    )


def open_insert_variable_dialog(app: AnycalcApp) -> None:
    """Offer the variables that already have a value for use in an expression.

    Picking one appends it to the expression, multiplying implicitly when the
    expression already ends on a number, a name or a closing bracket. With nothing
    set yet the dialog says so instead of opening an empty list.
    """
    page = app.page
    variables = app.variables

    if not variables:
        page.show_dialog(
            ft.AlertDialog(
                title="Insert Variable",
                content=ft.Text("Set a variable first."),
                actions=[
                    ft.TextButton(
                        content="OK",
                        on_click=lambda: page.pop_dialog(),
                    ),
                ],
            )
        )
        return

    async def insert_selected(name):
        if app.result_mode:
            app.expression = ""
        elif app.expression and (
            app.expression[-1].isdigit()
            or app.expression[-1].isalpha()
            or app.expression[-1] == ")"
        ):
            app.expression += "*"

        app.expression += name
        app.result_mode = False
        app.update_display()
        page.pop_dialog()
        page.update()

    variable_buttons = []
    for name in VARIABLE_NAMES:
        if name not in variables:
            continue

        async def click_variable(e, variable=name):
            del e
            await insert_selected(variable)

        variable_buttons.append(
            ft.TextButton(
                content=f"{name} = {variables[name]}",
                on_click=click_variable,
            )
        )

    page.show_dialog(
        ft.AlertDialog(
            title="Insert Variable",
            content=ft.Column(
                variable_buttons,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=320,
            ),
            actions=[
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda: page.pop_dialog(),
                ),
            ],
        )
    )
