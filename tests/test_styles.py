from types import SimpleNamespace
from typing import cast

import flet as ft
import pytest

import styles
from pi_view import PiView
from ui import AnycalcApp


def test_theme_list_contains_default_and_light_palettes() -> None:
    assert styles.DEFAULT_THEME.name == "Dark"
    assert {theme.name for theme in styles.THEMES} == {"Dark", "Light"}
    assert styles.get_theme("Light").app_background != (
        styles.get_theme("Dark").app_background
    )


def test_active_theme_updates_palette_constants_and_can_be_restored() -> None:
    original_name = styles.DEFAULT_THEME.name
    styles.set_active_theme("Light")
    try:
        assert styles.APP_BACKGROUND == styles.get_theme("Light").app_background
        assert styles.TEXT_PRIMARY == styles.get_theme("Light").text_primary
    finally:
        styles.set_active_theme(original_name)


def test_unknown_theme_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown theme"):
        styles.get_theme("Sepia")


def test_app_theme_selection_recolors_existing_controls() -> None:
    styles.set_active_theme("Dark")
    dark = styles.get_theme("Dark")
    content = ft.Text("Calculator", color=dark.text_primary)
    surface = ft.Container(content=content, bgcolor=dark.panel_background)
    detached_content = ft.Text("Pi", color=dark.text_primary)
    detached_surface = ft.Container(
        content=detached_content,
        bgcolor=dark.panel_background,
    )
    page = cast(
        ft.Page,
        SimpleNamespace(
            controls=[surface],
            drawer=None,
            end_drawer=None,
            update=lambda: None,
        ),
    )
    app = AnycalcApp.__new__(AnycalcApp)
    app.page = page
    app.selected_theme = "Dark"
    app.pi_view = cast(PiView, SimpleNamespace(root=detached_surface))

    try:
        app.apply_theme("Light")

        assert page.bgcolor == styles.get_theme("Light").app_background
        assert surface.bgcolor == styles.get_theme("Light").panel_background
        assert content.color == styles.get_theme("Light").text_primary
        assert detached_surface.bgcolor == styles.get_theme("Light").panel_background
        assert detached_content.color == styles.get_theme("Light").text_primary
        assert page.theme_mode == ft.ThemeMode.LIGHT
    finally:
        styles.set_active_theme("Dark")


def test_settings_dialog_lists_the_available_themes() -> None:
    app = AnycalcApp.__new__(AnycalcApp)
    app.selected_theme = "Dark"
    app.page = cast(ft.Page, SimpleNamespace(pop_dialog=lambda: None))

    dialog = app.build_settings_dialog()

    assert dialog.key == "settings-dialog"
    assert dialog.modal is True
    assert app.settings_theme_group.value == "Dark"
    assert isinstance(app.settings_theme_group.content, ft.Column)
    radios = app.settings_theme_group.content.controls
    assert all(isinstance(radio, ft.Radio) for radio in radios)
    assert [radio.label for radio in radios if isinstance(radio, ft.Radio)] == [
        "Dark",
        "Light",
    ]
