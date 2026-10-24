"""anycalc's entry point.

The app itself lives in ``ui.py`` and the arithmetic in ``calculate.py`` and
``conversions.py``; this module only hands the app to Flet. It is the module
Flet is pointed at (``[tool.flet.app] module = "main"`` in pyproject.toml).

``src/`` is the app's *import root*, not a package: Flet packages the contents
of the app directory as the built app's root, and pytest gets the same root
from ``pythonpath = ["src"]``. That is why every module here, this one
included, imports its siblings by bare name (``from ui import AnycalcApp``) -
the same import works in the workspace and inside the built app.

Importing this module - which the tests do - must never open a window, so
``ft.run`` only happens when the module is executed as ``__main__``.
"""

import flet as ft

from ui import AnycalcApp


def main(page: ft.Page) -> None:
    """Build one AnythingCalculator window on ``page``."""

    AnycalcApp(page).build()


def run_app() -> None:
    """Start anycalc.

    Entry point for ``flet run`` (Flet calls ``main`` itself, so this is for
    plain ``python src/main.py`` and for importing the module and starting the
    app by hand).
    """

    ft.run(main)


if __name__ == "__main__":
    run_app()
