"""The "Follow system theme" option: one dropdown entry, no palette of its own.

No app host is needed - ``pytest -k system_theme`` runs this on its own. The
app is built over the shared page stub in ``tests/stub_page.py``, whose
``platform_brightness`` stands in for what the host platform reports.
"""

import types
from typing import cast

import flet as ft
import pytest

import styles
from stub_page import StubPage, build_app


@pytest.fixture(autouse=True)
def _leave_the_live_theme_as_found():
    """Put back the palette an app started here replaced.

    The theme constants are process-wide, so the style tests must not see one
    left over from an app built over the page stub.
    """

    before = styles.get_active_theme()
    try:
        yield
    finally:
        styles.set_active_theme(before.name)


def test_the_system_entry_is_not_a_palette_and_is_still_recognised() -> None:
    assert styles.is_system_theme(styles.SYSTEM_THEME_NAME)
    assert not styles.is_system_theme(styles.DEFAULT_THEME.name)

    assert styles.SYSTEM_THEME_NAME not in [theme.name for theme in styles.THEMES]


def test_brightness_picks_the_matching_built_in_palette() -> None:
    assert styles.system_theme(ft.Brightness.DARK) is styles.get_theme("Dark")
    assert styles.system_theme(ft.Brightness.LIGHT) is styles.get_theme("Light")

    # A platform that never answers keeps the app's own default.
    assert styles.system_theme(None) is styles.DEFAULT_THEME


def test_the_settings_dropdown_leads_with_the_system_entry() -> None:
    app = build_app()
    app.build_settings_dialog()

    options = [option.key for option in app.settings_theme_dropdown.options]

    assert options[0] == styles.SYSTEM_THEME_NAME
    assert options[1:] == [theme.name for theme in styles.THEMES]


def test_following_the_system_hands_the_material_brightness_to_flet() -> None:
    app = build_app()

    app.apply_theme(styles.SYSTEM_THEME_NAME)

    assert app.selected_theme == styles.SYSTEM_THEME_NAME
    assert app.page.theme_mode == ft.ThemeMode.SYSTEM  # type: ignore[attr-defined]


def test_the_palette_follows_the_platform_the_app_starts_on() -> None:
    app = build_app()
    page = cast(StubPage, app.page)
    page.platform_brightness = ft.Brightness.LIGHT

    app.apply_theme(styles.SYSTEM_THEME_NAME)

    assert app.page.bgcolor == styles.get_theme("Light").app_background
    assert styles.get_active_theme().name == "Light"


def test_a_platform_change_recolors_only_while_following_the_system() -> None:
    app = build_app()
    page = cast(StubPage, app.page)
    app.apply_theme(styles.SYSTEM_THEME_NAME)
    assert app.page.bgcolor == styles.DEFAULT_THEME.app_background

    page.platform_brightness = ft.Brightness.LIGHT
    app.handle_platform_brightness(types.SimpleNamespace())

    assert app.page.bgcolor == styles.get_theme("Light").app_background

    app.apply_theme("Dark")
    page.platform_brightness = ft.Brightness.DARK
    app.handle_platform_brightness(types.SimpleNamespace())

    assert app.selected_theme == "Dark"
    assert app.page.bgcolor == styles.get_theme("Dark").app_background


def test_the_system_entry_keeps_the_color_settings_for_custom_only() -> None:
    app = build_app()
    app.build_settings_dialog()

    app._sync_color_visibility(styles.SYSTEM_THEME_NAME)

    assert app.settings_primary_group.visible is False
    assert app.settings_secondary_group.visible is False


def test_a_saved_system_theme_loads_as_a_theme() -> None:
    app = build_app()
    page = cast(StubPage, app.page)
    page.platform_brightness = ft.Brightness.LIGHT

    assert app._saved_theme(styles.SYSTEM_THEME_NAME) == styles.get_theme("Light")

    try:
        app._saved_theme("Not a theme")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown saved theme must be reported")
