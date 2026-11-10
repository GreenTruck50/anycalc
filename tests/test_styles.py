from types import SimpleNamespace
from typing import cast

import flet as ft
from flet_color_pickers import ColorPicker
import pytest

import styles
from pi_view import PiView
from ui import AnycalcApp


def test_theme_list_offers_more_than_dark_and_light() -> None:
    names = [theme.name for theme in styles.THEMES]

    assert styles.DEFAULT_THEME.name == "Dark"
    assert names[0] == "Dark"
    assert styles.CUSTOM_THEME_NAME in names
    assert {
        "Dark",
        "Light",
        "Midnight",
        "Forest",
        "Sepia",
        "High contrast",
    } <= set(names)

    assert styles.get_theme("Light").app_background != (
        styles.get_theme("Dark").app_background
    )
    # The built-in themes are genuinely different palettes, not renames - only
    # the Custom theme starts out on Dark's surfaces.
    built_in = [name for name in names if name != styles.CUSTOM_THEME_NAME]
    surfaces = {styles.get_theme(name).app_background for name in built_in}
    assert len(surfaces) == len(built_in)
    assert styles.get_theme(styles.CUSTOM_THEME_NAME).app_background == (
        styles.get_theme("Dark").app_background
    )


def test_custom_theme_is_the_entry_that_takes_user_colors() -> None:
    custom = styles.get_theme(styles.CUSTOM_THEME_NAME)

    assert custom.name == styles.CUSTOM_THEME_NAME
    # It is a theme like any other, but never the one the app starts on.
    assert styles.DEFAULT_THEME is not custom
    assert styles.THEMES[-1] is custom


def test_named_colors_offer_several_shades_per_family() -> None:
    names = {option.name for option in styles.COLOR_OPTIONS}

    assert {"Green", "Dark green", "Forest green", "Olive", "Lime", "Emerald"} <= names
    assert {"Blue", "Royal blue", "Sky blue", "Navy", "Indigo"} <= names
    assert {"Teal", "Turquoise", "Cyan"} <= names

    # Every entry is selectable as a color: unique names, unique values, and a
    # value the color validator accepts as-is.
    assert len(names) == len(styles.COLOR_OPTIONS)
    values = [option.value for option in styles.COLOR_OPTIONS]
    assert len(values) == len(set(values))
    for option in styles.COLOR_OPTIONS:
        assert styles.normalize_color(option.value) == option.value


def test_theme_default_accents_are_named_color_options() -> None:
    """The palette has to name what the themes default to.

    "Reset to defaults" puts a theme's own accent and operator-key colors back
    into the dropdowns, so those values have to exist as named options rather
    than landing on the "Custom color" entry.
    """

    values = {option.value for option in styles.COLOR_OPTIONS}
    for theme in styles.THEMES:
        assert theme.accent in values
        assert theme.key_operator in values
        assert styles.is_named_color(theme.accent)
        assert styles.is_named_color(theme.key_operator)


def test_color_options_lead_with_the_custom_color_entry() -> None:
    options = styles.color_options()

    assert options[0].value == styles.CUSTOM_COLOR_KEY
    assert options[0].name == "Custom color"
    assert options[1:] == styles.COLOR_OPTIONS
    # The entry is a mode, not a color: it never joins the named palette.
    assert styles.CUSTOM_COLOR_KEY not in {
        option.value for option in styles.COLOR_OPTIONS
    }
    assert not styles.is_named_color(styles.CUSTOM_COLOR_KEY)


def test_the_custom_color_entry_names_the_hex_it_holds() -> None:
    assert styles.custom_color_label(styles.DEFAULT_THEME.accent) == "Custom color"
    assert styles.custom_color_label("#123456") == "Custom color (#123456)"
    assert styles.custom_color_label("#12abcd") == "Custom color (#12ABCD)"
    assert styles.custom_color_label("green") == "Custom color"

    # The caption under a revealed picker always names the live color.
    assert styles.custom_color_value_label("#123456") == "Custom color: #123456"
    assert styles.custom_color_value_label("#12abcd") == "Custom color: #12ABCD"
    assert styles.custom_color_value_label("green") == "Custom color"


def test_picker_colors_fold_into_six_digit_hex() -> None:
    assert styles.picker_color("#22c55e") == "#22C55E"
    assert styles.picker_color(" #ef4444 ") == "#EF4444"
    # The picker reports "#AARRGGBB" while alpha is on.
    assert styles.picker_color("#FF22C55E") == "#22C55E"

    for unusable in ("", None, "green", "#12345"):
        with pytest.raises(ValueError, match="six-digit hexadecimal"):
            styles.picker_color(unusable)


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
        styles.get_theme("Watercolor")


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
        styles.SYSTEM_THEME_NAME,
        *(theme.name for theme in styles.THEMES),
    ]
    assert app.settings_primary_dropdown.value == styles.DEFAULT_THEME.accent
    assert app.settings_secondary_dropdown.value == styles.DEFAULT_THEME.key_operator
    for dropdown in (
        app.settings_primary_dropdown,
        app.settings_secondary_dropdown,
    ):
        # Every named entry carries a swatch of its own color ...
        assert all(
            isinstance(option.leading_icon, ft.Icon)
            and option.leading_icon.color == option.key
            and option.text is not None
            for option in dropdown.options[1:]
        )
        # ... and the list leads with the entry that opens a color picker.
        assert dropdown.options[0].key == styles.CUSTOM_COLOR_KEY
        assert dropdown.options[0].text == "Custom color"
    assert any(
        option.text == "Blue" for option in app.settings_primary_dropdown.options
    )
    assert any(
        option.text == "Light gray"
        for option in app.settings_secondary_dropdown.options
    )
    # The wider palette reaches the dialog, not just styles.COLOR_OPTIONS.
    assert any(
        option.text == "Forest green"
        for option in app.settings_primary_dropdown.options
    )


def test_color_settings_are_hidden_until_the_custom_theme_is_picked() -> None:
    styles.set_active_theme("Dark")
    page = settings_page()
    app = settings_app(page)
    try:
        app.build_settings_dialog()

        # A built-in theme ships its own accents, so there is nothing to pick.
        assert app.settings_primary_group.visible is False
        assert app.settings_secondary_group.visible is False
        assert not revealed(app, app.settings_primary_picker)

        app.settings_theme_dropdown.value = "Midnight"
        app.update_settings(None)
        assert app.settings_primary_group.visible is False

        app.settings_theme_dropdown.value = styles.CUSTOM_THEME_NAME
        app.update_settings(None)

        assert app.settings_primary_group.visible is True
        assert app.settings_secondary_group.visible is True
        # The pickers wait for their own dropdown entry.
        assert not revealed(app, app.settings_primary_picker)

        app.settings_primary_dropdown.value = styles.CUSTOM_COLOR_KEY
        app.update_settings(None)

        assert revealed(app, app.settings_primary_picker)
        assert not revealed(app, app.settings_secondary_picker)
        # The picker arrives with the caption naming the color that is live.
        assert revealed(app, app.settings_primary_value)
        assert app.settings_primary_value.value == (
            f"Custom color: {styles.DEFAULT_THEME.accent}"
        )
        assert not revealed(app, app.settings_secondary_value)
        # Revealing a picker changes nothing about the colors in use.
        assert styles.ACCENT == styles.DEFAULT_THEME.accent
        assert page.saved == 3
    finally:
        styles.set_active_theme("Dark")


def settings_page() -> SimpleNamespace:
    """A page stand-in for the settings handlers.

    It records whether a handler closed the dialog and whether it asked for a
    save, which is what tells "applied and kept open" apart from "applied on
    Apply".
    """

    page = SimpleNamespace(
        controls=[],
        drawer=None,
        end_drawer=None,
        popped=0,
        saved=0,
    )
    page.update = lambda *controls: None
    page.show_dialog = lambda dialog: None
    page.pop_dialog = lambda: setattr(page, "popped", page.popped + 1)
    page.run_task = lambda task, *args: setattr(page, "saved", page.saved + 1)
    return page


def settings_app(page: SimpleNamespace) -> AnycalcApp:
    """An app carrying just what the settings handlers reach for."""

    app = AnycalcApp.__new__(AnycalcApp)
    app.page = cast(ft.Page, page)
    app.selected_theme = styles.DEFAULT_THEME.name
    app.selected_primary_color = styles.DEFAULT_THEME.accent
    app.selected_secondary_color = styles.DEFAULT_THEME.key_operator
    app.pi_view = None
    return app


def revealed(app: AnycalcApp, control: ft.Control) -> bool:
    """Whether a color caption or picker is currently in the column that lays its
    setting out.

    Those two are revealed by being put into that column - and taken back out of
    it - rather than by a `visible` flag, because on Flet 1.1 flipping only that
    flag on a control whose parent still has the same child list never repaints
    it. The whole color group still hides behind a flag.
    """

    return any(
        child is control
        for column in (
            app.settings_primary_content,
            app.settings_secondary_content,
        )
        for child in column.controls
    )


def test_settings_dialog_applies_its_own_choices_without_an_apply_button() -> None:
    app = AnycalcApp.__new__(AnycalcApp)
    app.selected_theme = styles.DEFAULT_THEME.name
    app.selected_primary_color = styles.DEFAULT_THEME.accent
    app.selected_secondary_color = styles.DEFAULT_THEME.key_operator
    app.page = cast(ft.Page, SimpleNamespace(pop_dialog=lambda: None))

    dialog = app.build_settings_dialog()

    # Every dropdown applies what it changed the moment it changes.
    for dropdown in (
        app.settings_theme_dropdown,
        app.settings_primary_dropdown,
        app.settings_secondary_dropdown,
    ):
        assert dropdown.on_select is not None

    # Applying is left to the dropdowns: the actions are two plain text buttons,
    # no filled Apply button, and they only reset and close.
    labels = [
        action.content
        for action in dialog.actions or []
        if isinstance(action, ft.TextButton)
    ]
    assert labels == ["Close", "Reset to defaults"]
    assert len(dialog.actions or []) == len(labels)


def test_picking_a_theme_or_color_applies_without_closing() -> None:
    styles.set_active_theme("Dark")
    page = settings_page()
    app = settings_app(page)
    try:
        app.build_settings_dialog()

        # A built-in theme lands on its own accents the moment it is picked.
        app.settings_theme_dropdown.value = "Light"
        app.update_settings(None)

        assert app.selected_theme == "Light"
        assert styles.APP_BACKGROUND == styles.get_theme("Light").app_background
        assert styles.ACCENT == styles.get_theme("Light").accent
        assert page.saved == 1
        assert page.popped == 0

        # A hand-picked color lands just as immediately, on the Custom theme -
        # which is picked first, since the color settings only appear with it.
        app.settings_theme_dropdown.value = styles.CUSTOM_THEME_NAME
        app.update_settings(None)
        app.settings_primary_dropdown.value = "#22C55E"
        app.update_settings(None)

        assert app.selected_primary_color == "#22C55E"
        assert styles.ACCENT == "#22C55E"
        assert styles.KEY_OPERATOR == styles.get_theme(
            styles.CUSTOM_THEME_NAME
        ).key_operator
        assert page.saved == 3
        assert page.popped == 0
    finally:
        styles.set_active_theme("Dark")


def test_a_builtin_theme_keeps_its_own_accents_and_the_custom_colors() -> None:
    styles.set_active_theme(styles.CUSTOM_THEME_NAME)
    page = settings_page()
    app = settings_app(page)
    app.selected_theme = styles.CUSTOM_THEME_NAME
    app.selected_primary_color = "#22C55E"
    app.selected_secondary_color = "#EC4899"
    try:
        app.build_settings_dialog()
        app.settings_theme_dropdown.value = "Dark"
        app.update_settings(None)

        # A built-in theme never borrows the picked colors ...
        assert styles.ACCENT == styles.get_theme("Dark").accent
        assert styles.KEY_OPERATOR == styles.get_theme("Dark").key_operator
        # ... and it does not spend them either.
        assert app.selected_primary_color == "#22C55E"
        assert app.selected_secondary_color == "#EC4899"
        assert app.settings_primary_group.visible is False

        # Coming back to the Custom theme restores them, dropdowns included.
        app.settings_theme_dropdown.value = styles.CUSTOM_THEME_NAME
        app.update_settings(None)

        assert styles.ACCENT == "#22C55E"
        assert styles.KEY_OPERATOR == "#EC4899"
        assert app.settings_primary_dropdown.value == "#22C55E"
        assert app.settings_primary_picker.color == "#22C55E"
    finally:
        styles.set_active_theme("Dark")


def test_picking_a_color_in_a_picker_applies_it_at_once() -> None:
    styles.set_active_theme(styles.CUSTOM_THEME_NAME)
    page = settings_page()
    app = settings_app(page)
    app.selected_theme = styles.CUSTOM_THEME_NAME
    try:
        app.build_settings_dialog()
        app.settings_primary_dropdown.value = styles.CUSTOM_COLOR_KEY
        app.update_settings(None)
        assert app.settings_primary_picker.visible is True
        app.settings_primary_picker.color = "#12ABCD"

        app.pick_primary_color(picker_event(app.settings_primary_picker, "#12abcd"))

        assert app.selected_primary_color == "#12ABCD"
        assert styles.ACCENT == "#12ABCD"
        assert app.selected_secondary_color == styles.get_theme(
            styles.CUSTOM_THEME_NAME
        ).key_operator
        # The entry now names the picked color, so the list shows it too.
        option = app.settings_primary_dropdown.options[0]
        assert option.text == "Custom color (#12ABCD)"
        assert isinstance(option.leading_icon, ft.Icon)
        assert option.leading_icon.color == "#12ABCD"
        assert app.settings_primary_value.value == "Custom color: #12ABCD"
        assert app.settings_primary_value.visible is True
        assert page.saved == 2
        assert page.popped == 0
    finally:
        styles.set_active_theme("Dark")


def picker_event(picker: ColorPicker, data: str) -> ft.Event[ColorPicker]:
    """The event a color picker hands its handler."""

    return cast(
        ft.Event[ColorPicker],
        SimpleNamespace(data=data, control=picker),
    )


def test_reset_to_defaults_restores_default_theme_and_colors_immediately() -> None:
    styles.set_active_theme(styles.CUSTOM_THEME_NAME)
    page = settings_page()
    app = settings_app(page)
    app.selected_theme = styles.CUSTOM_THEME_NAME
    app.selected_primary_color = "#22C55E"
    app.selected_secondary_color = "#123456"
    try:
        app.build_settings_dialog()
        app.settings_primary_dropdown.value = styles.CUSTOM_COLOR_KEY
        app.settings_primary_picker.color = "#22C55E"
        app.update_settings(None)
        assert styles.ACCENT == "#22C55E"
        assert app.settings_primary_group.visible is True

        app.reset_settings(None)

        # The dropdowns show the defaults again and the app is already using them.
        assert app.settings_theme_dropdown.value == styles.DEFAULT_THEME.name
        assert app.settings_primary_dropdown.value == styles.DEFAULT_THEME.accent
        assert (
            app.settings_secondary_dropdown.value
            == styles.DEFAULT_THEME.key_operator
        )
        assert app.selected_theme == styles.DEFAULT_THEME.name
        assert app.selected_primary_color == styles.DEFAULT_THEME.accent
        assert styles.APP_BACKGROUND == styles.DEFAULT_THEME.app_background
        assert styles.ACCENT == styles.DEFAULT_THEME.accent
        assert styles.KEY_OPERATOR == styles.DEFAULT_THEME.key_operator
        # Reset picks a built-in theme, so the color settings hide themselves
        # again on the way out.
        assert app.settings_primary_group.visible is False
        assert app.settings_primary_picker.visible is False
        assert page.saved == 2
        assert page.popped == 0
    finally:
        styles.set_active_theme("Dark")


def test_a_saved_custom_color_selects_the_custom_color_entry() -> None:
    app = AnycalcApp.__new__(AnycalcApp)
    app.selected_theme = styles.CUSTOM_THEME_NAME
    app.selected_primary_color = "#123456"
    app.selected_secondary_color = styles.DEFAULT_THEME.key_operator
    app.page = cast(ft.Page, SimpleNamespace(pop_dialog=lambda: None))

    app.build_settings_dialog()

    # A color outside the named list puts the dropdown on the entry that opens a
    # picker - and that picker is already showing, holding the saved color.
    assert app.settings_primary_group.visible is True
    assert app.settings_primary_dropdown.value == styles.CUSTOM_COLOR_KEY
    assert app.settings_primary_picker.visible is True
    assert app.settings_primary_picker.color == "#123456"
    assert app.settings_primary_value.visible is True
    assert app.settings_primary_value.value == "Custom color: #123456"
    option = app.settings_primary_dropdown.options[0]
    assert option.text == "Custom color (#123456)"
    assert isinstance(option.leading_icon, ft.Icon)
    assert option.leading_icon.color == "#123456"

    # A named color needs no picker at all.
    assert app.settings_secondary_group.visible is True
    assert app.settings_secondary_dropdown.value == styles.DEFAULT_THEME.key_operator
    assert app.settings_secondary_picker.visible is False


def test_reset_to_defaults_drops_a_saved_custom_color() -> None:
    styles.set_active_theme(styles.CUSTOM_THEME_NAME)
    page = settings_page()
    app = settings_app(page)
    app.selected_theme = styles.CUSTOM_THEME_NAME
    app.selected_primary_color = "#123456"
    try:
        app.build_settings_dialog()
        assert app.settings_primary_dropdown.value == styles.CUSTOM_COLOR_KEY
        assert app.settings_primary_dropdown.options[0].text == (
            "Custom color (#123456)"
        )

        app.reset_settings(None)

        assert app.selected_primary_color == styles.DEFAULT_THEME.accent
        assert app.settings_primary_dropdown.value == styles.DEFAULT_THEME.accent
        assert app.settings_primary_picker.color == styles.DEFAULT_THEME.accent
        assert app.settings_primary_dropdown.options[0].text == "Custom color"
    finally:
        styles.set_active_theme("Dark")


def test_only_the_custom_theme_takes_hand_picked_colors() -> None:
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
        # A built-in theme applies its own accents and leaves the saved custom
        # colors alone for the Custom theme to use.
        app.apply_settings_selection("Light", "#123456", "#ABCDEF")

        assert app.selected_theme == "Light"
        assert app.selected_primary_color == styles.DEFAULT_THEME.accent
        assert styles.ACCENT == styles.get_theme("Light").accent
        assert styles.KEY_OPERATOR == styles.get_theme("Light").key_operator

        app.apply_settings_selection(styles.CUSTOM_THEME_NAME, "#123456", "#ABCDEF")

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
