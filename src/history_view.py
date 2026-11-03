"""The calculation history: one card per equation, and the drawer holding them.

The app owns the history list and what a click inserts; this module only turns an
``(equation, answer)`` pair into the card the user sees.
"""

from typing import Callable

import flet as ft

import styles

_CALCULATOR_STATUSES = frozenset({"REGULAR MODE", "SCIENTIFIC MODE"})


# A click handler for a history card; the app closes the drawer afterwards.
HistoryClick = Callable[[ft.Event[ft.TextButton]], object]


def history_notice_visible(status: str) -> bool:
    """Whether the current page is outside the two calculators."""

    return status not in _CALCULATOR_STATUSES


def build_history_card(
    equation: str,
    answer: str,
    on_equation: HistoryClick,
    on_answer: HistoryClick,
    copy_button: ft.Control,
) -> ft.Container:
    """One entry: the equation and the answer, each tappable and copyable."""

    answer_controls: list[ft.Control] = [
        ft.TextButton(
            content=answer,
            tooltip="Insert answer",
            on_click=on_answer,
            expand=True,
        ),
        copy_button,
    ]
    card_controls: list[ft.Control] = [
        ft.Text(
            "EXPRESSION",
            size=10,
            color=styles.TEXT_MUTED,
        ),
        ft.TextButton(
            content=equation,
            tooltip="Insert equation",
            on_click=on_equation,
            expand=True,
        ),
        ft.Text(
            "RESULT",
            size=10,
            color=styles.TEXT_MUTED,
        ),
        ft.Row(
            answer_controls,
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ]
    return ft.Container(
        content=ft.Column(
            card_controls,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        bgcolor=styles.CARD_BACKGROUND,
        border_radius=10,
        padding=6,
        width=320,
    )


def build_history_drawer(
    history_list: ft.Column,
    scope_notice: ft.Text,
    on_clear: HistoryClick,
) -> ft.NavigationDrawer:
    """The end drawer: scrollable cards plus the button that empties them."""

    return ft.NavigationDrawer(
        width=320,
        bgcolor=styles.PANEL_BACKGROUND,
        controls=[
            ft.Container(
                content=ft.Text(
                    "Calculation history",
                    size=19,
                    weight=ft.FontWeight.BOLD,
                ),
                padding=16,
            ),
            ft.Container(
                content=scope_notice,
                padding=ft.Padding.symmetric(horizontal=16, vertical=4),
            ),
            ft.Divider(),
            ft.Container(
                content=history_list,
                expand=True,
                padding=8,
            ),
            ft.Row(
                [
                    ft.Container(expand=True),
                    ft.TextButton(
                        content="Clear history",
                        on_click=on_clear,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ],
    )
