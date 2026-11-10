"""A page stand-in good enough to build the whole app without an app host.

``AnycalcApp.build()`` only ever asks the page to update itself, add controls,
run a task, or show and pop a dialog, so this answers those and counts them. The
tests that exercise app behaviour - the keyboard, the memory keys, the variable
dialogs - build the real app over it instead of needing a Flet window.
"""

import inspect
import types
from typing import cast

import flet as ft

from ui import AnycalcApp


class StubPage:
    """Just enough of a page for ``AnycalcApp.build()``: it updates and runs tasks."""

    def __init__(self) -> None:
        self.width: int | float | None = 400
        self.height: int | float | None = 780
        self.window = types.SimpleNamespace(
            width=None, height=None, min_width=None, min_height=None
        )
        # The page tree a theme switch walks to recolor what is on screen. The app
        # fills these in as it builds, and the stub only has to survive the walk.
        self.controls: list[ft.Control] = []
        self.drawer: ft.NavigationDrawer | None = None
        self.end_drawer: ft.NavigationDrawer | None = None
        # What the "System" theme reads. Tests set this to watch the app follow.
        self.platform_brightness: ft.Brightness | None = None
        self.updates = 0
        self.tasks: list[str] = []
        self.dialogs: list[object] = []
        self.popped = 0

    def update(self, *_controls: ft.Control) -> None:
        del _controls
        self.updates += 1

    def add(self, *_controls: ft.Control) -> None:
        self.controls.extend(_controls)

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


def build_app() -> AnycalcApp:
    """The whole app over a stub page, opening on the regular pad."""

    app = AnycalcApp(cast(ft.Page, StubPage()))
    app.build()
    return app


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


def switch_event(value: bool) -> types.SimpleNamespace:
    """The payload a ``ft.Switch`` hands its ``on_change`` handler."""

    return types.SimpleNamespace(control=types.SimpleNamespace(value=value))
