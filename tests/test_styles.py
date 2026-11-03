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


def test_active_theme_applies_custom_primary_and_secondary_colors() -> None:
    styles.set_active_theme("Dark", "#123456", "#ABCDEF")
    try:
        assert styles.ACCENT == "#123456"
        assert styles.KEY_OPERATOR == "#ABCDEF"
        assert styles.active_palette()["ACCENT"] == "#123456"
        assert styles.KEY_INK == styles.get_theme("Dark").key_ink
    finally:
        styles.set_active_theme("Dark")


def test_unknown_theme_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown theme"):
        styles.get_theme("Sepia")


def test_invalid_custom_color_does_not_change_the_active_palette() -> None:
    styles.set_active_theme("Dark", "#123456", "#ABCDEF")
    original_palette = styles.active_palette()
    try:
        with pytest.raises(ValueError, match="six-digit hexadecimal"):
            styles.set_active_theme("Light", "")

        assert styles.active_palette() == original_palette
        assert styles.APP_BACKGROUND == styles.get_theme("Dark").app_background
    finally:
        styles.set_active_theme("Dark")


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
    app.selected_primary_color = styles.get_theme("Dark").accent
    app.selected_secondary_color = styles.get_theme("Dark").key_operator
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


def test_settings_dialog_has_named_color_dropdowns_with_indicators() -> None:
    app = AnycalcApp.__new__(AnycalcApp)
    app.selected_theme = "Dark"
    app.selected_primary_color = styles.DEFAULT_THEME.accent
    app.selected_secondary_color = styles.DEFAULT_THEME.key_operator
    app.page = cast(ft.Page, SimpleNamespace(pop_dialog=lambda: None))

    dialog = app.build_settings_dialog()

    assert dialog.key == "settings-dialog"
    assert dialog.modal is True
    assert app.settings_theme_dropdown.value == "Dark"
    assert [option.text for option in app.settings_theme_dropdown.options] == [
        "Dark",
        "Light",
    ]
    assert app.settings_primary_dropdown.value == styles.DEFAULT_THEME.accent
    assert app.settings_secondary_dropdown.value == styles.DEFAULT_THEME.key_operator
    for dropdown in (
        app.settings_primary_dropdown,
        app.settings_secondary_dropdown,
    ):
        assert all(
            isinstance(option.leading_icon, ft.Icon)
            and option.leading_icon.color == option.key
            and option.text is not None
            for option in dropdown.options
        )
    assert any(option.text == "Blue" for option in app.settings_primary_dropdown.options)
    assert any(
        option.text == "Light gray"
        for option in app.settings_secondary_dropdown.options
    )


def test_saved_custom_color_is_shown_as_a_named_dropdown_option() -> None:
    app = AnycalcApp.__new__(AnycalcApp)
    app.selected_theme = "Dark"
    app.selected_primary_color = "#123456"
    app.selected_secondary_color = styles.DEFAULT_THEME.key_operator
    app.page = cast(ft.Page, SimpleNamespace(pop_dialog=lambda: None))

    app.build_settings_dialog()

    custom_option = app.settings_primary_dropdown.options[-1]
    assert custom_option.key == "#123456"
    assert custom_option.text == "Custom (#123456)"
    assert isinstance(custom_option.leading_icon, ft.Icon)
    assert custom_option.leading_icon.color == "#123456"


def test_app_applies_custom_colors_with_the_selected_theme() -> None:
    styles.set_active_theme("Dark")
    page = cast(
        ft.Page,
        SimpleNamespace(
            controls=[],
            drawer=None,
            end_drawer=None,
            update=lambda: None,
        ),
    )
    app = AnycalcApp.__new__(AnycalcApp)
    app.page = page
    app.selected_theme = "Dark"
    app.selected_primary_color = styles.DEFAULT_THEME.accent
    app.selected_secondary_color = styles.DEFAULT_THEME.key_operator
    app.pi_view = None

    try:
        app.apply_settings_selection("Light", "#123456", "#ABCDEF")

        assert app.selected_theme == "Light"
        assert app.selected_primary_color == "#123456"
        assert app.selected_secondary_color == "#ABCDEF"
        assert styles.ACCENT == "#123456"
        assert styles.KEY_OPERATOR == "#ABCDEF"
        assert page.theme is not None
        assert page.theme.color_scheme is not None
        assert page.theme.color_scheme.primary == "#123456"
        assert page.theme.color_scheme.secondary == "#ABCDEF"
    finally:
        styles.set_active_theme("Dark")
