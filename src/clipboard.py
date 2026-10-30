"""One clipboard, backing every copy button in the app."""

from typing import Any, Callable

import flet as ft

from styles import TEXT_MUTED, TEXT_PRIMARY

# How much of a copied value the confirmation snackbar shows before truncating.
CLIPBOARD_PREVIEW_LIMIT = 40


class ClipboardService:
    """Copies a value to the system clipboard and confirms it in a snackbar.

    The ``ft.Clipboard`` is constructed inside the page session - that is what
    registers the service - so exactly one of these is built while the app is
    built, and every copy button in the app shares it.
    """

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.clipboard = ft.Clipboard()

    @staticmethod
    def preview(text: str, limit: int = CLIPBOARD_PREVIEW_LIMIT) -> str:
        return text if len(text) <= limit else f"{text[:limit]}…"

    async def copy(self, value: Any) -> None:
        text = "" if value is None else str(value)
        if not text.strip():
            self.page.show_dialog(ft.SnackBar(ft.Text("Nothing to copy yet")))
            return

        try:
            await self.clipboard.set(text)
        except Exception as error:
            self.page.show_dialog(ft.SnackBar(ft.Text(f"Copy failed: {error}")))
            return

        self.page.show_dialog(
            ft.SnackBar(ft.Text(f"Copied {self.preview(text)}"))
        )

    def make_button(
        self,
        get_value: Callable[[], Any],
        tooltip: str = "Copy",
    ) -> ft.IconButton:
        """Small icon-only copy button reading its value when clicked."""

        async def handle_copy(e):
            del e
            await self.copy(get_value())

        return ft.IconButton(
            icon=ft.Icons.CONTENT_COPY,
            icon_size=16,
            icon_color=TEXT_MUTED,
            hover_color=TEXT_PRIMARY,
            size_constraints=ft.BoxConstraints(
                min_width=30,
                min_height=30,
                max_width=30,
                max_height=30,
            ),
            tooltip=tooltip,
            on_click=handle_copy,
        )
