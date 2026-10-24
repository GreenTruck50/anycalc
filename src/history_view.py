"""The calculation history: one card per equation, and the drawer holding them.

The app owns the history list and what a click inserts; this module only turns an
``(equation, answer)`` pair into the card the user sees.
"""

from typing import Awaitable, Callable

import flet as ft

from styles import CARD_BACKGROUND, PANEL_BACKGROUND, TEXT_MUTED

# A click handler for a history card; the app closes the drawer afterwards.
HistoryClick = Callable[[ft.ControlEvent], Awaitable[None]]


def build_history_card(
    equation: str,
    answer: str,
    on_equation: HistoryClick,
    on_answer: HistoryClick,
    copy_button: ft.IconButton,
) -> ft.Container:
    """One entry: the equation and the answer, each tappable and copyable."""

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "EXPRESSION",
                    size=10,
                    color=TEXT_MUTED,
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
                    color=TEXT_MUTED,
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            content=answer,
                            tooltip="Insert answer",
                            on_click=on_answer,
                            expand=True,
                        ),
                        copy_button,
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        bgcolor=CARD_BACKGROUND,
        border_radius=10,
        padding=6,
        width=320,
    )


def build_history_drawer(
    history_list: ft.Column,
    on_clear,
) -> ft.NavigationDrawer:
    """The end drawer: scrollable cards plus the button that empties them."""

    return ft.NavigationDrawer(
        width=320,
        bgcolor=PANEL_BACKGROUND,
        controls=[
            ft.Container(
                content=ft.Text(
                    "Calculation history",
                    size=19,
                    weight=ft.FontWeight.BOLD,
                ),
                padding=16,
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
