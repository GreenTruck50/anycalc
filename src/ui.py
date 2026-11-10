"""The app itself: page setup, display state, keypad wiring and navigation.

``AnycalcApp`` owns the state that used to live in the closures of a single
``main(page)`` function - the expression on the display, whether the display
rests on a result, the DEG/RAD setting, the named variables and the history - and
wires it to the pieces built elsewhere: the key rows (``src/keypad.py``), the
conversion form (``src/conversion_view.py``), the history drawer
(``src/history_view.py``), the variable dialogs (``src/variable_dialogs.py``) and
the shared clipboard (``src/clipboard.py``). ``src/main.py`` only builds and runs
this, and the arithmetic itself never lives here - it is asked for from
``src/calculate.py`` and ``src/conversions.py``.
"""

import asyncio
import re
from collections.abc import Callable
from decimal import Decimal
from typing import cast

import flet as ft
from flet_color_pickers import ColorPicker

from calculate import calculate, is_number, toggle_sign
from clipboard import ClipboardService
from config import (
    DEFAULT_HISTORY_LENGTH,
    DISPLAY_TEXT_SIZE,
    ERROR_MESSAGES,
    ERROR_VARIABLES_DISABLED,
    HISTORY_LENGTH_CHOICES,
    MAX_HISTORY_ITEMS,
    PREVIEW_MORPH_LIFT,
    PREVIEW_MORPH_MS,
    PREVIEW_TEXT_SIZE,
    VARIABLE_NAMES,
)
from conversion_view import ConversionView
from conversions import load_conversion_config
from currency_view import CurrencyConversionView
from data_storage import AppDataStore, AppState
from history_view import (
    build_history_card,
    build_history_drawer,
    history_notice_visible,
)
from keypad import (
    CLEAR_VARIABLES_KEY,
    DIALOG_KEYS,
    MEMORY_CLEAR_KEY,
    MEMORY_ROW,
    key_color,
    make_key,
    pad_key,
    pad_rows,
)
import pi
import pi_value
from pi_view import PiView
from precision import (
    DECIMAL_PLACE_CHOICES,
    DEFAULT_ROUNDING,
    ROUNDING_LABELS,
    ROUNDING_MODES,
    SCIENTIFIC_THRESHOLD_CHOICES,
    SIGNIFICANT_FIGURE_CHOICES,
    Precision,
    format_answer,
)
import styles
from variable_dialogs import open_insert_variable_dialog, open_set_variable_dialog

# The arrow keys walk the stored history into the display; the value says whether
# the walk steps back in time (the newest entry first) or forward again.
HISTORY_WALK_KEYS = {"ArrowUp": True, "ArrowDown": False}


class AnycalcApp:
    """The AnythingCalculator window: two calculator pads and the conversions."""

    # The settings dialog gets built on an app instance that was never started -
    # the style tests do exactly that - so the pad settings carry their defaults
    # on the class rather than only on a started instance.
    memory_keys_on_scientific: bool = False
    precision: Precision = Precision()
    history_limit: int = DEFAULT_HISTORY_LENGTH

    def __init__(self, page: ft.Page) -> None:
        self.page = page

        self.conversion_unit_groups, self.conversion_options = load_conversion_config()
        self.conversion_groups_by_name = {
            group["name"]: group for group in self.conversion_unit_groups
        }
        self.conversion_unit_labels = {
            unit["id"]: f"{unit['name']} ({unit['symbol']})"
            for group in self.conversion_unit_groups
            for unit in group["units"]
        }

        # What the display holds: the expression, and whether it currently shows a
        # result rather than what the user typed.
        self.scientific = False
        self.degrees = True
        self.expression = ""
        self.result_mode = False
        self.variables: dict[str, Decimal] = {}
        self.history: list[tuple[str, str]] = []
        self.selected_theme = styles.DEFAULT_THEME.name
        self.selected_primary_color = styles.DEFAULT_THEME.accent
        self.selected_secondary_color = styles.DEFAULT_THEME.key_operator

        # The conversion form currently in the content area, if any.
        self.conversion_view: ConversionView | None = None
        self.currency_view: CurrencyConversionView | None = None

        # The pi page, built the first time it is opened.
        self.pi_view: PiView | None = None

        # The physical keyboard: whether one of the two calculator pads is on
        # screen at all, and whether a text field holds the caret - a focused
        # field types its own keys, so the handler has to stay out of its way.
        self.calculator_showing = True
        self.text_field_focused = False

        # How far back into the history the arrow keys have walked; None while
        # what is on the display is the user's own entry.
        self.history_walk: int | None = None

        # The calculator memory: what M+ / M- store, and whether MRC has just put
        # it back into the expression (a second MRC right after that clears it).
        # The regular pad always carries the keys; the scientific pad only does
        # while the setting that asks for them there is on.
        self.memory: Decimal | None = None
        self.memory_recalled = False
        self.memory_keys_on_scientific = False

        # How answers are rounded and written out once they are calculated.
        self.precision = Precision()

        # How many finished calculations the history keeps.
        self.history_limit = DEFAULT_HISTORY_LENGTH

        # Install a safe computed pi immediately, then restore the last adopted
        # value from client storage before enabling controls in the built page.
        self.program_pi_run = pi_value.install_default_pi()
        self.data_store = AppDataStore()

        # The live answer grows into the display when "=" is pressed. The token
        # tells the finishing task whether it is still the promotion in flight.
        self.preview_morphing = False
        self.preview_morph_token = 0

        # System clipboard service: constructing it inside the page session registers
        # it automatically, so a single instance backs every copy button in the app.
        self.clipboard = ClipboardService(page)

    # ----------------------------
    # Building the window
    # ----------------------------

    def build(self) -> None:
        """Assemble the page. Handlers read the controls below them, so the order
        only matters for what ends up in the tree, not for what runs later."""

        page = self.page
        styles.set_active_theme(
            self.selected_theme,
            self.selected_primary_color,
            self.selected_secondary_color,
        )
        page.title = "AnythingCalculator"
        page.theme_mode = self._theme_mode(styles.DEFAULT_THEME)
        page.bgcolor = styles.APP_BACKGROUND
        page.padding = 16

        # A physical keyboard presses the same pad a tap does; the gates that keep
        # it out of other people's keys are in handle_keyboard_event.
        page.on_keyboard_event = self.handle_keyboard_event

        # The "System" theme follows the host platform, so it has to hear when the
        # platform moves between light and dark.
        page.on_platform_brightness_change = self.handle_platform_brightness

        # Mobile renders edge-to-edge, so the system bars are given the page colour
        # and light icons instead of floating over the app in their own colours. The
        # bars stay visible; the content that used to sit under them is pushed clear
        # by the SafeArea the page is built inside (see the bottom of this method).
        page.theme = self._make_page_theme(styles.DEFAULT_THEME)

        page.window.width = 400
        page.window.height = 780
        page.window.min_width = 320
        page.window.min_height = 500

        self._build_display()

        self.status = ft.Text("REGULAR MODE", size=12, color=styles.TEXT_MUTED)
        self.variable_status = ft.Text(
            "",
            size=11,
            color=styles.TEXT_MUTED,
            visible=False,
        )
        # The memory, listed the way the variables are: "M = 42" on the line under
        # the display, which is the line the pad's shared row owns.
        self.memory_status = ft.Text(
            "",
            size=11,
            color=styles.TEXT_MUTED,
            visible=False,
        )
        self.history_list = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.history_scope_notice = ft.Text(
            "History only applies to the Regular and Scientific Calculators.",
            size=11,
            color=styles.TEXT_MUTED,
            visible=False,
            key="history-scope-notice",
        )

        self._build_header()
        self._build_display_panel()
        self.keypad = ft.Column(
            spacing=8,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self._build_history_drawer()
        self._build_navigation_drawer()

        self.rebuild_keypad()

        self.calculator_view = ft.Column(
            [
                self.display_panel,
                self.keypad,
            ],
            spacing=12,
            expand=True,
        )
        self.content_area = ft.Column(
            [self.calculator_view],
            expand=True,
        )
        self.header.disabled = True
        self.content_area.disabled = True

        # The SafeArea insets the whole window by whatever the operating system
        # occupies - the status bar at the top, the notch, the navigation bar at the
        # bottom - which on desktop is nothing at all. spacing stays at 0 because the
        # page laid its two children out without a gap before this wrapper existed.
        page.add(
            ft.SafeArea(
                content=ft.Column(
                    [self.header, self.content_area],
                    spacing=0,
                    expand=True,
                ),
                expand=True,
            )
        )
        page.run_task(self.load_saved_data)

    def _theme_mode(self, theme: styles.AppTheme) -> ft.ThemeMode:
        """The Material brightness the app asks Flet for.

        Following the system means handing that decision to Flet; every palette
        the app owns states its own brightness.
        """

        if styles.is_system_theme(self.selected_theme):
            return ft.ThemeMode.SYSTEM
        return ft.ThemeMode.DARK if theme.mode == "dark" else ft.ThemeMode.LIGHT

    @staticmethod
    def _make_page_theme(theme: styles.AppTheme) -> ft.Theme:
        brightness = (
            ft.Brightness.DARK if theme.mode == "dark" else ft.Brightness.LIGHT
        )
        icon_brightness = (
            ft.Brightness.LIGHT if theme.mode == "dark" else ft.Brightness.DARK
        )
        return ft.Theme(
            color_scheme_seed=styles.ACCENT,
            color_scheme=ft.ColorScheme(
                primary=styles.ACCENT,
                secondary=styles.KEY_OPERATOR,
            ),
            system_overlay_style=ft.SystemOverlayStyle(
                status_bar_color=theme.app_background,
                status_bar_brightness=brightness,
                status_bar_icon_brightness=icon_brightness,
                system_navigation_bar_color=theme.app_background,
                system_navigation_bar_divider_color=theme.app_background,
                system_navigation_bar_icon_brightness=icon_brightness,
            ),
        )

    def _recolor_controls(
        self,
        old_palette: dict[str, str],
        new_palette: dict[str, str],
    ) -> None:
        """Replace palette colours on the controls currently in the page tree."""

        color_changes = {
            old_color: new_palette[name]
            for name, old_color in old_palette.items()
        }
        pending: list[ft.BaseControl] = list(self.page.controls)
        if self.page.drawer is not None:
            pending.append(self.page.drawer)
        if self.page.end_drawer is not None:
            pending.append(self.page.end_drawer)
        if self.pi_view is not None and self.pi_view.root is not None:
            pending.append(self.pi_view.root)
        visited: set[int] = set()
        color_properties = (
            "bgcolor",
            "color",
            "icon_color",
            "hover_color",
            "ink_color",
        )

        while pending:
            control = pending.pop()
            identity = id(control)
            if identity in visited:
                continue
            visited.add(identity)

            for property_name in color_properties:
                color = getattr(control, property_name, None)
                replacement = (
                    color_changes.get(color) if isinstance(color, str) else None
                )
                if replacement is not None:
                    setattr(control, property_name, replacement)

            children = getattr(control, "controls", None)
            if children:
                pending.extend(
                    child for child in children if isinstance(child, ft.BaseControl)
                )
            content = getattr(control, "content", None)
            if isinstance(content, ft.BaseControl):
                pending.append(content)

    def _saved_theme(self, name: str) -> styles.AppTheme:
        """The palette a saved theme name stands for, "System" included.

        A name that is neither a built-in nor the system entry is the one case
        that has to be reported to the user - the saved data is older than the
        app reading it.
        """

        if styles.is_system_theme(name):
            return styles.system_theme(self.page.platform_brightness)
        return styles.get_theme(name)

    def apply_theme(self, name: str) -> None:
        """Make one theme live, recoloring the controls already on screen.

        Only the Custom theme takes hand-picked accent colors. Every built-in
        theme ships its own, and the Custom theme's saved colors survive a trip
        through them untouched.

        "System" is not a palette: it borrows whichever built-in the host
        platform's brightness asks for right now, and stays selected so the app
        keeps following the system as that changes.
        """

        old_palette = styles.active_palette()
        if name == styles.CUSTOM_THEME_NAME:
            overrides: tuple[str | None, str | None] = (
                self.selected_primary_color,
                self.selected_secondary_color,
            )
        else:
            overrides = (None, None)
        if styles.is_system_theme(name):
            applied = styles.system_theme(self.page.platform_brightness).name
        else:
            applied = name
        _, new_theme = styles.set_active_theme(applied, *overrides)
        self.selected_theme = name if styles.is_system_theme(name) else new_theme.name
        self._recolor_controls(old_palette, styles.active_palette())
        self.page.bgcolor = new_theme.app_background
        self.page.theme_mode = self._theme_mode(new_theme)
        self.page.theme = self._make_page_theme(new_theme)
        self.page.update()

    def handle_platform_brightness(self, event: object) -> None:
        """The host platform changed between light and dark.

        Only the "System" theme cares: a hand-picked theme stays exactly as it was
        picked, whatever the operating system does around it.
        """

        del event
        if not styles.is_system_theme(self.selected_theme):
            return
        self.apply_theme(styles.SYSTEM_THEME_NAME)

    def apply_settings_selection(
        self,
        name: str,
        primary_color: str,
        secondary_color: str,
    ) -> None:
        """Apply one settings choice.

        The two colors are only kept for the Custom theme - a built-in theme
        always comes with its own accents, and switching to one leaves the
        colors saved for the Custom theme alone.
        """

        if not styles.is_system_theme(name):
            styles.get_theme(name)
        if name == styles.CUSTOM_THEME_NAME:
            self.selected_primary_color = styles.normalize_color(primary_color)
            self.selected_secondary_color = styles.normalize_color(secondary_color)
        self.apply_theme(name)

    def persist_pi_change(self) -> None:
        self.page.run_task(self.save_data, True)

    def _state_snapshot(self, include_pi: bool = False) -> AppState:
        return AppState(
            theme=self.selected_theme,
            history=tuple(self.history[-self.history_limit:]),
            pi_text=pi.program_pi_text() if include_pi else None,
            pi_digits=pi.program_pi_digits() if include_pi else None,
            primary_color=self.selected_primary_color,
            secondary_color=self.selected_secondary_color,
            memory_keys_on_scientific=self.memory_keys_on_scientific,
            precision=self.precision,
            history_limit=self.history_limit,
        )

    async def load_saved_data(self) -> None:
        """Restore saved state once the page and its storage service are ready."""

        try:
            state = await self.data_store.load()
            if state is None:
                await self.save_data(include_pi=True)
                return

            try:
                theme = self._saved_theme(state.theme)
            except ValueError as error:
                self._show_storage_error(f"Saved theme could not be used: {error}")
            else:
                self.selected_primary_color = (
                    state.primary_color or theme.accent
                )
                self.selected_secondary_color = (
                    state.secondary_color or theme.key_operator
                )
                self.apply_theme(state.theme)

            self.history = list(state.history)
            self.history_limit = state.history_limit
            self.refresh_history()
            self.memory_keys_on_scientific = state.memory_keys_on_scientific
            self.precision = state.precision
            self.rebuild_keypad()
            if state.pi_text is not None and state.pi_digits is not None:
                whole, separator, decimals = state.pi_text.partition(".")
                if whole != "3" or not separator or len(decimals) != state.pi_digits:
                    raise ValueError("saved pi digits do not match their precision")
                pi.set_program_pi(
                    Decimal(state.pi_text),
                    state.pi_digits,
                    decimals,
                )
                if self.pi_view is not None:
                    self.pi_view.refresh_current()
            self.page.update()
        except (OSError, ValueError) as error:
            self._show_storage_error(f"Saved data could not be loaded: {error}")
        finally:
            self.header.disabled = False
            self.content_area.disabled = False
            self.page.update()

    async def save_data(self, include_pi: bool = False) -> None:
        """Persist current app state and report client-storage failures."""

        try:
            await self.data_store.save(self._state_snapshot(include_pi))
        except (OSError, ValueError) as error:
            self._show_storage_error(f"App data could not be saved: {error}")

    def _show_storage_error(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    def _build_display(self) -> None:
        """The caption above the display, the display field, its copy button and
        the live answer's slot underneath."""

        self.expression_label = ft.Text(
            "EXPRESSION",
            size=11,
            color=styles.TEXT_MUTED,
        )

        self.display = ft.TextField(
            # key: stable handle for the integration tests in tests/ (see the Flet
            # integration-testing docs) - it has no effect on what the user sees.
            key="display",
            value="0",
            text_size=DISPLAY_TEXT_SIZE,
            color=styles.TEXT_PRIMARY,
            text_align=ft.TextAlign.RIGHT,
            border=ft.NoInputBorder(),
            content_padding=0,
            expand=True,
            on_change=lambda e: self.handle_display_change(e.control.value),
            on_focus=lambda e: self.select_result(e.control),
            # Enter commits what is in the field, the way "=" does on the pad -
            # the field eats its own printable keys, so this is the one key the
            # keyboard handler cannot do for it while the caret sits here.
            on_submit=lambda e: self.handle_key("="),
        )

        self.copy_display_button = self.clipboard.make_button(
            lambda: self.display.value,
            tooltip="Copy displayed value",
        )

        # The live answer: a small grey number under the display box that follows
        # the expression while it is being typed. Pressing "=" promotes it into the
        # display instead of letting it vanish.
        self.preview_value = ft.Text(
            "",
            size=PREVIEW_TEXT_SIZE,
            color=styles.TEXT_MUTED,
            text_align=ft.TextAlign.RIGHT,
            animate_size=ft.Animation(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
        )
        self.preview_slot = ft.Container(
            content=self.preview_value,
            alignment=ft.Alignment.CENTER_RIGHT,
            animate_size=ft.Animation(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
            animate_offset=ft.Animation(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
            animate_opacity=ft.Animation(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_IN,
            ),
            visible=False,
        )

        # The display is an editable field, so while it holds the caret its typing
        # arrives as on_change and must not also be pressed on the pad.
        self.watch_field_focus(self.display)

    def _build_header(self) -> None:
        """Menu button, title and caption, plus history and settings."""

        self.header = ft.Row(
            [
                ft.IconButton(
                    key="menu-button",
                    icon=ft.Icons.MENU,
                    icon_color=styles.TEXT_PRIMARY,
                    tooltip="Calculator menu",
                    on_click=self.open_menu,
                ),
                ft.Column(
                    [
                        ft.Text(
                            "AnythingCalculator",
                            size=19,
                            weight=ft.FontWeight.BOLD,
                        ),
                        self.status,
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.IconButton(
                    key="settings-button",
                    icon=ft.Icons.SETTINGS,
                    icon_color=styles.TEXT_PRIMARY,
                    tooltip="Settings",
                    on_click=self.open_settings,
                ),
                ft.IconButton(
                    icon=ft.Icons.HISTORY,
                    icon_color=styles.TEXT_PRIMARY,
                    tooltip="Calculation history",
                    on_click=self.open_history,
                ),
            ],
        )

        self.angle_label = ft.Text("DEG")
        self.angle_button = ft.TextButton(
            content=self.angle_label,
            on_click=self.toggle_angle,
        )

    def build_settings_dialog(self) -> ft.AlertDialog:
        """The settings popup. Every dropdown applies what it changed straight
        away, which is why the dialog has no Apply button - the Close action only
        closes, and "Reset to defaults" puts the app's own defaults back.

        The two color settings belong to the Custom theme and are hidden for
        every built-in theme, which ships its own accents. Under each color
        dropdown the leading "Custom color" entry keeps a color picker hidden
        until that entry is picked.
        """

        self.settings_theme_dropdown = ft.Dropdown(
            key="settings-theme-dropdown",
            label="Theme",
            value=self.selected_theme,
            options=[
                ft.DropdownOption(key=theme, text=theme)
                for theme in (
                    styles.SYSTEM_THEME_NAME,
                    *(built_in.name for built_in in styles.THEMES),
                )
            ],
            on_select=self.update_settings,
        )
        (
            self.settings_primary_group,
            self.settings_primary_content,
            self.settings_primary_dropdown,
            self.settings_primary_value,
            self.settings_primary_picker,
        ) = self._build_color_setting(
            key="settings-primary-color",
            label="Primary color",
            color=self._seed_color(self.selected_primary_color),
            on_color_change=self.pick_primary_color,
        )
        (
            self.settings_secondary_group,
            self.settings_secondary_content,
            self.settings_secondary_dropdown,
            self.settings_secondary_value,
            self.settings_secondary_picker,
        ) = self._build_color_setting(
            key="settings-secondary-color",
            label="Secondary color",
            color=self._seed_color(self.selected_secondary_color),
            on_color_change=self.pick_secondary_color,
        )
        self.settings_memory_switch = ft.Switch(
            key="settings-memory-keys",
            label="Memory keys on the scientific pad (replaces the variable keys)",
            value=self.memory_keys_on_scientific,
            on_change=self.update_memory_keys_setting,
        )
        # The precision box: how an answer is rounded and written out. Every
        # dropdown applies the moment it is picked, like the rest of the dialog.
        self.settings_precision_decimals = self._build_precision_dropdown(
            key="settings-precision-decimals",
            label="Decimal places",
            value=self.precision.decimals,
            choices=DECIMAL_PLACE_CHOICES,
        )
        self.settings_precision_sig_figs = self._build_precision_dropdown(
            key="settings-precision-significant-figures",
            label="Significant figures",
            value=self.precision.sig_figs,
            choices=SIGNIFICANT_FIGURE_CHOICES,
        )
        self.settings_precision_scientific = self._build_precision_dropdown(
            key="settings-precision-scientific-notation",
            label="Scientific notation from",
            value=self.precision.sci_threshold,
            choices=SCIENTIFIC_THRESHOLD_CHOICES,
            power_labels=True,
        )
        self.settings_precision_rounding = ft.Dropdown(
            key="settings-precision-rounding",
            label="Rounding",
            value=self.precision.rounding,
            options=[
                ft.DropdownOption(key=mode, text=label)
                for mode, label in ROUNDING_LABELS.items()
            ],
            on_select=self.update_precision,
        )
        self.settings_history_length = ft.Dropdown(
            key="settings-history-length",
            label="History length",
            value=str(self.history_limit),
            options=[
                ft.DropdownOption(key=str(choice), text=f"Keep {choice}")
                for choice in HISTORY_LENGTH_CHOICES
            ],
            on_select=self.update_history_length,
        )
        self.settings_clear_history_button = ft.TextButton(
            key="settings-clear-history",
            content="Clear history",
            on_click=self.clear_history,
        )
        self.settings_reset_button = ft.TextButton(
            key="settings-reset-all-data",
            content="Reset all app data",
            on_click=self.open_reset_confirmation,
        )
        self.settings_content = ft.Column(
            [
                self.settings_theme_dropdown,
                self.settings_memory_switch,
                self.settings_precision_decimals,
                self.settings_precision_sig_figs,
                self.settings_precision_scientific,
                self.settings_precision_rounding,
                self.settings_history_length,
                ft.Row(
                    [
                        self.settings_clear_history_button,
                        self.settings_reset_button,
                    ],
                    spacing=8,
                ),
                self.settings_primary_group,
                self.settings_secondary_group,
            ],
            height=460,
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )
        self.settings_dialog = ft.AlertDialog(
            key="settings-dialog",
            modal=True,
            title=ft.Text("Settings"),
            content=self.settings_content,
            actions=[
                ft.TextButton(
                    content="Close",
                    key="settings-close",
                    on_click=self.close_settings,
                ),
                ft.TextButton(
                    content="Reset to defaults",
                    key="settings-reset",
                    on_click=self.reset_settings,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        return self.settings_dialog

    def _build_color_setting(
        self,
        key: str,
        label: str,
        color: str,
        on_color_change: Callable[[ft.Event[ColorPicker]], None],
    ) -> tuple[ft.Container, ft.Column, ft.Dropdown, ft.Text, ColorPicker]:
        """One color setting: dropdown, the hex it stands for, and a picker.

        The dropdown leads with "Custom color" and then lists the named palette;
        picking that entry reveals the picker and the caption naming the live
        hex, and the picker's own value is what gets applied. The three travel in
        one container so a built-in theme can hide all of them at once, and the
        column that lays them out is handed back as well - the caption and the
        picker are revealed by being in that column's child list or not in it (see
        ``_sync_color_visibility``), and that column is what carries the change
        into an update (see ``_update_settings_dialog``).
        """

        uses_custom = not styles.is_named_color(color)
        options = [
            self._color_dropdown_option(option, color)
            for option in styles.color_options()
        ]
        dropdown = ft.Dropdown(
            key=key,
            label=label,
            value=styles.CUSTOM_COLOR_KEY if uses_custom else color,
            options=options,
            on_select=self.update_settings,
        )
        value_label = ft.Text(
            key=f"{key}-value",
            value=styles.custom_color_value_label(color),
            size=12,
            color=styles.TEXT_MUTED,
        )
        picker = ColorPicker(
            key=f"{key}-picker",
            color=color,
            enable_alpha=False,
            color_picker_width=260,
            on_color_change=on_color_change,
        )
        # The caption and the picker are only in the column's child list while
        # they are wanted - see _sync_color_visibility for why they are revealed
        # that way rather than by hiding them.
        children: list[ft.Control] = [dropdown]
        if uses_custom:
            children += [value_label, picker]
        content = ft.Column(children, spacing=6)
        group = ft.Container(
            key=f"{key}-group",
            visible=self.selected_theme == styles.CUSTOM_THEME_NAME,
            content=content,
        )
        return group, content, dropdown, value_label, picker

    @staticmethod
    def _color_dropdown_option(
        option: styles.NamedColor,
        selected_color: str,
    ) -> ft.DropdownOption:
        """One entry of a color dropdown: a named color, or the picker entry.

        The "Custom color" entry carries the picked hex in its label and a
        swatch of it, so the choice is readable from the list itself.
        """

        if option.value != styles.CUSTOM_COLOR_KEY:
            return ft.DropdownOption(
                key=option.value,
                text=option.name,
                leading_icon=ft.Icon(ft.Icons.CIRCLE, size=16, color=option.value),
            )
        return ft.DropdownOption(
            key=styles.CUSTOM_COLOR_KEY,
            text=styles.custom_color_label(selected_color),
            leading_icon=ft.Icon(
                ft.Icons.BRUSH,
                size=16,
                color=(
                    selected_color
                    if not styles.is_named_color(selected_color)
                    else None
                ),
            ),
        )

    async def open_settings(self, event: object) -> None:
        del event
        self.page.show_dialog(self.build_settings_dialog())
        self.page.update()

    def close_settings(self, event: object) -> None:
        del event
        self.page.pop_dialog()
        self.page.update()

    def update_settings(self, event: object) -> None:
        """Apply the dropdown that just changed, while the dialog stays open.

        Nothing waits for an Apply button: picking a theme or a color recolors
        the app the moment it is picked and is saved straight away. Moving to the
        Custom theme also reveals the color settings that belong to it.
        """

        del event
        self._apply_settings_from_dialog()

    def update_memory_keys_setting(self, event) -> None:
        """Ask for the memory keys on the scientific pad, or stop asking.

        The switch applies the way every other setting does - straight away, with
        no Apply button - so the pad on screen is rebuilt to carry the memory row
        in place of the variable row (or the variable row back again), the variable
        line under the display appears or disappears with it, and the choice is
        saved with the rest of the settings.
        """

        self.memory_keys_on_scientific = bool(event.control.value)
        # Turning the memory keys off hands the row back to the variables, and the
        # memory goes with the row - see leave_memory_mode().
        if self.variables_enabled:
            self.leave_memory_mode()
        self.rebuild_keypad()
        self.refresh_variable_status()
        self.update_display()
        self.page.run_task(self.save_data)

    def _build_precision_dropdown(
        self,
        key: str,
        label: str,
        value: int | None,
        choices: tuple[int | None, ...],
        power_labels: bool = False,
    ) -> ft.Dropdown:
        """One precision dropdown: "Automatic" plus the listed choices.

        The threshold dropdown labels its choices as the powers of ten they
        stand for; the decimal-place and significant-figure dropdowns just count.
        """

        def option_label(choice: int | None) -> str:
            if choice is None:
                return "Automatic"
            if power_labels:
                return f"1E+{choice} and 1E-{choice}"
            return str(choice)

        return ft.Dropdown(
            key=key,
            label=label,
            value="auto" if value is None else str(value),
            options=[
                ft.DropdownOption(
                    key="auto" if choice is None else str(choice),
                    text=option_label(choice),
                )
                for choice in choices
            ],
            on_select=self.update_precision,
        )

    @staticmethod
    def _precision_choice(dropdown: ft.Dropdown) -> int | None:
        """What one precision dropdown stands for: a count, or automatic."""

        value = dropdown.value
        if not isinstance(value, str) or value == "auto":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def update_precision(self, event: object) -> None:
        """Apply the precision the dialog's precision box now holds.

        Like every other setting there is no Apply button: the answer on screen is
        re-shown under the new precision the moment a choice is made, and the
        choice is saved with the rest of the settings.
        """

        del event
        rounding = self.settings_precision_rounding.value
        if not isinstance(rounding, str) or rounding not in ROUNDING_MODES:
            rounding = DEFAULT_ROUNDING
        self.precision = Precision(
            decimals=self._precision_choice(self.settings_precision_decimals),
            sig_figs=self._precision_choice(self.settings_precision_sig_figs),
            sci_threshold=self._precision_choice(
                self.settings_precision_scientific
            ),
            rounding=rounding,
        )
        self.apply_precision()
        self.page.run_task(self.save_data)

    def apply_precision(self) -> None:
        """Re-show what is already on the display under the new precision."""

        if self.result_mode and is_number(self.expression):
            self.expression = format_answer(self.expression, self.precision)
        self.update_display()

    def format_result(self, answer: str) -> str:
        """One calculated answer, written the way the settings ask."""

        return format_answer(answer, self.precision)

    # ----------------------------
    # History length and the data reset
    # ----------------------------

    def update_history_length(self, event: object) -> None:
        """Keep fewer or more finished calculations.

        Shortening the history drops the oldest entries straight away - they are
        gone from the drawer, from the display's arrow-key walk and from what is
        saved, all at once.
        """

        del event
        choice = self.settings_history_length.value
        try:
            wanted = int(choice) if isinstance(choice, str) else 0
        except ValueError:
            wanted = DEFAULT_HISTORY_LENGTH
        self.history_limit = max(1, min(wanted, MAX_HISTORY_ITEMS))
        self.trim_history()
        self.refresh_history()
        self.page.update()
        self.page.run_task(self.save_data)

    def trim_history(self) -> None:
        """Cut the history back to what the current length allows."""

        if len(self.history) > self.history_limit:
            del self.history[: len(self.history) - self.history_limit]
        self.history_walk = None

    def open_reset_confirmation(self, event: object) -> None:
        """Ask first: a reset throws away work the user cannot get back."""

        del event
        self.page.show_dialog(
            ft.AlertDialog(
                key="reset-confirmation-dialog",
                modal=True,
                title=ft.Text("Reset all app data?"),
                content=ft.Text(
                    "This clears the calculation history, the saved variables and "
                    "the memory, forgets the pi the app adopted, and puts every "
                    "setting back to its default. It cannot be undone."
                ),
                actions=[
                    ft.TextButton(
                        key="reset-cancel",
                        content="Cancel",
                        on_click=self.close_reset_confirmation,
                    ),
                    ft.TextButton(
                        key="reset-confirm",
                        content="Reset",
                        on_click=self.confirm_reset_app_data,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )
        self.page.update()

    def close_reset_confirmation(self, event: object) -> None:
        del event
        self.page.pop_dialog()
        self.page.update()

    def confirm_reset_app_data(self, event: object) -> None:
        del event
        self.page.pop_dialog()
        self.reset_app_data()

    def reset_app_data(self) -> None:
        """Put the running app back to how it started, and clear what it stored."""

        defaults = styles.DEFAULT_THEME
        self.history.clear()
        self.history_limit = DEFAULT_HISTORY_LENGTH
        self.variables.clear()
        self.memory = None
        self.memory_recalled = False
        self.memory_keys_on_scientific = False
        self.precision = Precision()
        self.selected_primary_color = defaults.accent
        self.selected_secondary_color = defaults.key_operator
        self.expression = ""
        self.result_mode = False
        self.history_walk = None
        pi.reset_program_pi()
        if self.pi_view is not None:
            self.pi_view.refresh_current()

        self.refresh_history()
        self.refresh_variable_status()
        self.refresh_memory_status()
        self.sync_settings_controls()
        self.apply_theme(defaults.name)
        self.rebuild_keypad()
        self.reset_preview_slot()
        self.update_display()
        self.page.show_dialog(ft.SnackBar(ft.Text("All app data reset.")))
        self.page.run_task(self.store_reset_data)

    async def store_reset_data(self) -> None:
        """Write the emptied state over the top of everything that was stored."""

        try:
            await self.data_store.clear()
            await self.data_store.save(self._state_snapshot())
        except (OSError, ValueError) as error:
            self._show_storage_error(f"App data could not be reset: {error}")

    def sync_settings_controls(self) -> None:
        """Point an open settings dialog at what the app now holds.

        A reset changes settings without anyone tapping a dropdown, so the values
        in the dialog have to be moved in code - and pushed, since the dialog is
        still on screen.
        """

        if not hasattr(self, "settings_theme_dropdown"):
            return
        defaults = styles.DEFAULT_THEME
        self.settings_theme_dropdown.value = defaults.name
        self.settings_memory_switch.value = self.memory_keys_on_scientific
        self.settings_history_length.value = str(self.history_limit)
        for dropdown, choice in (
            (self.settings_precision_decimals, self.precision.decimals),
            (self.settings_precision_sig_figs, self.precision.sig_figs),
            (self.settings_precision_scientific, self.precision.sci_threshold),
        ):
            dropdown.value = "auto" if choice is None else str(choice)
        self.settings_precision_rounding.value = self.precision.rounding
        self._sync_color_settings()
        self._update_settings_dialog()

    def pick_primary_color(self, event: ft.Event[ColorPicker]) -> None:
        """The primary color's picker changed - apply it the same instant way."""

        self._apply_picked_color(self.settings_primary_dropdown, event)

    def pick_secondary_color(self, event: ft.Event[ColorPicker]) -> None:
        """The secondary color's picker changed - apply it the same instant way."""

        self._apply_picked_color(self.settings_secondary_dropdown, event)

    def _apply_picked_color(
        self,
        dropdown: ft.Dropdown,
        event: ft.Event[ColorPicker],
    ) -> None:
        """Apply and save the color a picker under a color dropdown reported.

        The dropdown stays on "Custom color", and both the entry's label and the
        caption under it start naming the picked hex.
        """

        try:
            color = styles.picker_color(event.data or event.control.color)
        except ValueError:
            return
        option = self._custom_option(dropdown)
        if option is not None:
            option.text = styles.custom_color_label(color)
            if isinstance(option.leading_icon, ft.Icon):
                option.leading_icon.color = color
        self._color_value_label(dropdown).value = (
            styles.custom_color_value_label(color)
        )
        if dropdown is self.settings_primary_dropdown:
            primary_color, secondary_color = color, self.selected_secondary_color
        else:
            primary_color, secondary_color = self.selected_primary_color, color
        self.apply_settings_selection(
            styles.CUSTOM_THEME_NAME,
            primary_color,
            secondary_color,
        )
        self._update_settings_dialog()
        self.page.run_task(self.save_data)

    def reset_settings(self, event: object) -> None:
        """Put the app's default theme and default accent colors back in the
        dropdowns, and apply them exactly like a hand-picked choice."""

        del event
        defaults = styles.DEFAULT_THEME
        self.selected_primary_color = defaults.accent
        self.selected_secondary_color = defaults.key_operator
        self.settings_theme_dropdown.value = defaults.name
        self._sync_color_settings()
        # The values were set in code rather than tapped, so it is the pushed
        # update inside this that shows them in the dialog that stays open.
        self._apply_settings_from_dialog()

    def _apply_settings_from_dialog(self) -> None:
        """Apply and save what the settings dialog currently holds."""

        name = self.settings_theme_dropdown.value
        if not isinstance(name, str):
            raise ValueError("the selected theme is invalid")
        if name == styles.CUSTOM_THEME_NAME:
            if self.selected_theme != styles.CUSTOM_THEME_NAME:
                # The Custom theme owns the color settings, so switching to it
                # hands its saved colors back to the dropdowns that appear.
                self._sync_color_settings()
            primary_color = self._dialog_color(
                self.settings_primary_dropdown,
                self.settings_primary_picker,
            )
            secondary_color = self._dialog_color(
                self.settings_secondary_dropdown,
                self.settings_secondary_picker,
            )
        else:
            if styles.is_system_theme(name):
                theme = styles.system_theme(self.page.platform_brightness)
            else:
                theme = styles.get_theme(name)
            primary_color, secondary_color = theme.accent, theme.key_operator
        # Reveal first: the page update inside apply_settings_selection is the one
        # that paints what switching to the Custom theme shows, so the child lists
        # have to be in place before it runs.
        self._sync_color_visibility(name)
        self.apply_settings_selection(name, primary_color, secondary_color)
        self._update_settings_dialog()
        self.page.run_task(self.save_data)

    @staticmethod
    def _seed_color(color: str) -> str:
        """A color the pickers and captions can name, or Custom's own default.

        Saved colors arrive as hex strings, but a value left by an older version
        still has to land on something the dialog can show.
        """

        try:
            return styles.normalize_color(color)
        except (TypeError, ValueError):
            return styles.get_theme(styles.CUSTOM_THEME_NAME).accent

    def _dialog_color(self, dropdown: ft.Dropdown, picker: ColorPicker) -> str:
        """The color one setting stands for: a named entry, or the picker.

        A picker that has not reported a usable color yet keeps this setting on
        the color it already had rather than failing the whole update.
        """

        value = dropdown.value
        if value != styles.CUSTOM_COLOR_KEY and isinstance(value, str):
            return value
        try:
            return styles.picker_color(picker.color)
        except ValueError:
            if dropdown is self.settings_primary_dropdown:
                return self.selected_primary_color
            return self.selected_secondary_color

    def _custom_option(self, dropdown: ft.Dropdown) -> ft.DropdownOption | None:
        """The "Custom color" entry of a color dropdown."""

        for option in dropdown.options or []:
            if option.key == styles.CUSTOM_COLOR_KEY:
                return option
        return None

    def _color_value_label(self, dropdown: ft.Dropdown) -> ft.Text:
        """The caption naming the color one color dropdown's setting stands for."""

        if dropdown is self.settings_primary_dropdown:
            return self.settings_primary_value
        return self.settings_secondary_value

    def _sync_color_settings(self) -> None:
        """Point both color dropdowns, captions and pickers at the Custom
        theme's colors."""

        for dropdown, value_label, picker, color in (
            (
                self.settings_primary_dropdown,
                self.settings_primary_value,
                self.settings_primary_picker,
                self.selected_primary_color,
            ),
            (
                self.settings_secondary_dropdown,
                self.settings_secondary_value,
                self.settings_secondary_picker,
                self.selected_secondary_color,
            ),
        ):
            color = self._seed_color(color)
            named = styles.is_named_color(color)
            dropdown.value = color if named else styles.CUSTOM_COLOR_KEY
            picker.color = color
            value_label.value = styles.custom_color_value_label(color)
            option = self._custom_option(dropdown)
            if option is not None:
                option.text = styles.custom_color_label(color)
                if isinstance(option.leading_icon, ft.Icon):
                    option.leading_icon.color = None if named else color

    def _sync_color_visibility(self, theme_name: str | None = None) -> None:
        """Show color settings only for the Custom theme, and a picker - with the
        caption naming its color - only while its dropdown is on "Custom color".

        ``theme_name`` is the theme being applied. The reveal has to be in place
        *before* that theme is pushed, because the page update inside
        ``apply_theme`` is what actually paints it - so this cannot just read the
        theme that is still live.

        Hiding a whole color setting is a ``visible`` flag on its container, which
        travels with the repaint a theme switch already causes. Revealing a picker
        inside a group that is already on screen is different: on Flet 1.1 a lone
        ``visible`` flip on a control whose parent still has the same child list
        never reaches the screen (measured - the flags were set and the update
        pushed without error, yet the caption stayed unpainted). What does reach it
        is changing that child list, so the caption and the picker are put into the
        group's column when they are wanted and taken out when they are not.
        """

        applied = self.selected_theme if theme_name is None else theme_name
        show_colors = applied == styles.CUSTOM_THEME_NAME
        self._sync_color_group(
            self.settings_primary_group,
            self.settings_primary_content,
            self.settings_primary_dropdown,
            self.settings_primary_value,
            self.settings_primary_picker,
            show_colors,
        )
        self._sync_color_group(
            self.settings_secondary_group,
            self.settings_secondary_content,
            self.settings_secondary_dropdown,
            self.settings_secondary_value,
            self.settings_secondary_picker,
            show_colors,
        )

    @staticmethod
    def _sync_color_group(
        group: ft.Container,
        content: ft.Column,
        dropdown: ft.Dropdown,
        value_label: ft.Text,
        picker: ColorPicker,
        show_colors: bool,
    ) -> None:
        """Put one color setting's picker and caption in or out of its column."""

        group.visible = show_colors
        use_picker = show_colors and dropdown.value == styles.CUSTOM_COLOR_KEY
        picker_is_shown = any(child is picker for child in content.controls)
        if use_picker == picker_is_shown:
            return
        content.controls = (
            [dropdown, value_label, picker] if use_picker else [dropdown]
        )

    def _update_settings_dialog(self) -> None:
        """Push the open dialog together with everything a setting reveals.

        A control that has only just become visible is not repainted by an update
        that names its parent alone, so the dialog, the columns that hold the
        settings, the color groups and their inner columns all go into the same
        update - and the inner column is what carries a caption or a picker that
        has just been added to it. The "Custom color" entry - whose label and
        swatch a picker renames as it is used - lives on the dropdowns, so they are
        named too. The captions and pickers themselves are not named: while their
        setting is on a built-in theme or a named color they are not in the tree at
        all (see ``_sync_color_visibility``), and updating a control that is out of
        the tree is what this keeps clear of.
        """

        self.page.update(
            self.settings_dialog,
            self.settings_content,
            self.settings_theme_dropdown,
            self.settings_memory_switch,
            self.settings_history_length,
            self.settings_primary_group,
            self.settings_primary_content,
            self.settings_secondary_group,
            self.settings_secondary_content,
            self.settings_primary_dropdown,
            self.settings_secondary_dropdown,
        )

    def _build_display_panel(self) -> None:
        """The panel that holds the caption row, the display and the preview."""

        self.display_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.expression_label,
                            ft.Container(expand=True),
                            self.copy_display_button,
                            self.angle_button,
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=self.display,
                        alignment=ft.Alignment.CENTER_RIGHT,
                        expand=True,
                    ),
                    self.preview_slot,
                    # The memory and the named variables share the line under the
                    # display: whichever row the pad is carrying owns that line, so
                    # only one of the two is ever on screen.
                    self.memory_status,
                    self.variable_status,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            bgcolor=styles.PANEL_BACKGROUND,
            border_radius=18,
            padding=16,
            height=168,
        )

    def _build_history_drawer(self) -> None:
        """The end drawer with the calculation history."""

        page = self.page
        page.end_drawer = build_history_drawer(
            self.history_list,
            self.history_scope_notice,
            self.clear_history,
        )

    def _build_navigation_drawer(self) -> None:
        """The start drawer: the title with its tagline, the two calculators, then
        every conversion entry."""

        self.drawer = ft.NavigationDrawer(
            selected_index=0,
            controls=[
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "AnythingCalculator",
                                size=22,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "Calculate anything.",
                                size=12,
                                color=styles.TEXT_MUTED,
                            ),
                        ],
                        spacing=2,
                    ),
                    # Tighter vertical padding than the old title-only block: the
                    # tagline costs the scrolling list a line of height, and every
                    # pixel here decides whether the last drawer entries render.
                    padding=ft.Padding.symmetric(horizontal=20, vertical=10),
                ),
                ft.Divider(),
                ft.Container(
                    content=ft.Text(
                        "Calculators",
                        size=12,
                        color=styles.TEXT_MUTED,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                ft.NavigationDrawerDestination(
                    key="drawer-regular-calculator",
                    icon=ft.Icons.CALCULATE,
                    label="Regular Calculator",
                ),
                ft.NavigationDrawerDestination(
                    key="drawer-scientific-calculator",
                    icon=ft.Icons.SCIENCE,
                    label="Scientific Calculator",
                ),
                ft.Divider(),
                ft.Container(
                    content=ft.Text(
                        "Unit Conversions",
                        size=12,
                        color=styles.TEXT_MUTED,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                *[
                    ft.NavigationDrawerDestination(
                        key=f"drawer-{conversion['name'].lower().replace(' ', '-')}",
                        icon=getattr(
                            ft.Icons, conversion["icon"].rsplit(".", 1)[-1]
                        ),
                        label=conversion["name"],
                    )
                    for conversion in self.conversion_options
                ],
                ft.Divider(),
                ft.Container(
                    content=ft.Text(
                        "Currency",
                        size=12,
                        color=styles.TEXT_MUTED,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                ft.NavigationDrawerDestination(
                    key="drawer-currency-conversion",
                    icon=ft.Icons.CURRENCY_EXCHANGE,
                    label="Currency Conversion",
                ),
                ft.Divider(),
                ft.Container(
                    content=ft.Text(
                        "Other",
                        size=12,
                        color=styles.TEXT_MUTED,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                ft.NavigationDrawerDestination(
                    key="drawer-pi-calculation",
                    icon=ft.Icons.SUPPORT,
                    label="Pi Calculation",
                ),
            ],
            on_change=self.handle_drawer_change,
        )

        self.page.drawer = self.drawer

    def handle_drawer_change(self, e) -> None:
        index = e.control.selected_index
        if index is None:
            return
        if index < 2:
            self.set_mode(index)
        elif index - 2 < len(self.conversion_options):
            self.open_conversion(self.conversion_options[index - 2])
        elif index - 2 == len(self.conversion_options):
            self.open_currency_conversion()
        else:
            self.open_pi()

    async def open_menu(self, e) -> None:
        del e
        await self.page.show_drawer()

    async def open_history(self, e) -> None:
        del e
        self.history_scope_notice.visible = history_notice_visible(
            self.status.value
        )
        await self.page.show_end_drawer()

    # ----------------------------
    # The display and its live answer
    # ----------------------------

    def refresh_copy_button_state(self) -> None:
        # Error strings are never worth pasting somewhere else.
        self.copy_display_button.disabled = (
            self.display.value or ""
        ) in ERROR_MESSAGES

    def preview_answer(self) -> str:
        """Evaluate the expression as it stands, or '' if it is incomplete.

        Half-typed expressions ("2+", "sqrt(") are normal while typing, so an
        unevaluable expression simply leaves the preview empty rather than
        reporting anything.
        """
        if not self.expression or self.expression in ERROR_MESSAGES:
            return ""

        try:
            answer = self.evaluate(self.expression)
        except Exception:
            return ""

        answer = self.format_result(answer)

        # A bare number is already the answer; showing it twice is noise.
        return "" if answer == self.expression else answer

    def reset_preview_slot(self) -> None:
        """Put the preview back at its small resting state, hidden."""
        self.preview_morphing = False
        self.preview_value.size = PREVIEW_TEXT_SIZE
        self.preview_value.color = styles.TEXT_MUTED
        self.preview_value.value = ""
        self.preview_slot.offset = ft.Offset(0, 0)
        self.preview_slot.opacity = 1
        self.preview_slot.visible = False

    def refresh_preview(self) -> None:
        """Keep the live answer in sync with the expression."""
        if self.preview_morphing:
            # A promotion into the display is mid-flight; do not fight it.
            return

        answer = "" if self.result_mode else self.preview_answer()
        self.preview_value.value = answer
        self.preview_slot.visible = bool(answer)

    async def finish_preview_morph(self, token: int) -> None:
        await asyncio.sleep(PREVIEW_MORPH_MS / 1000)
        if token != self.preview_morph_token:
            return
        self.reset_preview_slot()
        self.refresh_preview()
        self.page.update()

    def promote_preview(self) -> None:
        """Grow the live answer into the display: bigger, white, sliding up."""
        if not self.preview_slot.visible or not self.preview_value.value:
            return

        self.preview_morphing = True
        self.preview_morph_token += 1
        self.preview_value.size = DISPLAY_TEXT_SIZE
        self.preview_value.color = styles.TEXT_PRIMARY
        self.preview_slot.offset = ft.Offset(0, -PREVIEW_MORPH_LIFT)
        self.preview_slot.opacity = 0
        self.page.run_task(self.finish_preview_morph, self.preview_morph_token)

    def select_result(self, control) -> None:
        if self.result_mode:
            control.selection = ft.TextSelection(0, len(self.expression))

    def handle_display_change(self, value) -> None:
        if (
            self.result_mode
            and is_number(self.expression)
            and value in ("+", "-", "*", "/", "%", "^")
        ):
            value = self.expression + value

        self.expression = value
        self.result_mode = False
        self.history_walk = None
        self.expression_label.value = "EXPRESSION"
        self.display.value = self.expression
        self.refresh_copy_button_state()
        self.refresh_preview()
        self.page.update()

    def update_display(self) -> None:
        self.display.value = self.expression or "0"
        self.expression_label.value = "RESULT" if self.result_mode else "EXPRESSION"
        self.refresh_copy_button_state()
        self.refresh_preview()
        self.page.update()

    # ----------------------------
    # Keypad
    # ----------------------------

    def rebuild_keypad(self) -> None:
        """Put the pad back together: the rows this mode and settings ask for."""

        self.keypad.controls.clear()

        for row in pad_rows(self.scientific, self.memory_keys_on_scientific):
            self.keypad.controls.append(
                ft.Row(
                    [make_key(key, self.handle_key, key_color(key)) for key in row],
                    spacing=8,
                )
            )

        self.page.update()

    def handle_key(self, label: str) -> None:
        """Dispatch a key press: the variable keys open dialogs, the rest press."""

        if label not in DIALOG_KEYS:
            # Any key other than MRC ends a recall, so the next MRC recalls the
            # stored number again instead of clearing it.
            if label != "MRC":
                self.memory_recalled = False
            if label == CLEAR_VARIABLES_KEY:
                # The variable row's third key empties every variable; it is not a
                # key the expression can take.
                self.clear_variables()
                return
            self.press(label)
            return

        if label == "Set Variable":
            open_set_variable_dialog(self)
        else:
            open_insert_variable_dialog(self)

    def press(self, key):
        if key in MEMORY_ROW:
            # The memory keys work on the number the display rests on, so they
            # never edit the expression the way the other keys do - except MRC,
            # which puts the stored number in as if it had been typed.
            self.press_memory(key)
            return

        if key == "±":
            # A sign change edits the number that is already on the display, so
            # it bypasses the "any other key starts a new entry" rule below and
            # leaves result_mode alone: "-5" straight after "=" is still a result.
            if self.expression in ERROR_MESSAGES:
                self.expression = ""
            else:
                # The two pads read "%" differently, and "±" has to agree: on the
                # regular pad "200+10%" ends on a number, on the scientific pad
                # "200+10%" ends on an operator still waiting for one.
                self.expression = toggle_sign(
                    self.expression, percent_is_modulo=self.scientific
                )
            self.update_display()
            return

        if key != "=" and self.result_mode:
            if key == "AC":
                self.expression = ""
            elif is_number(self.expression) and key in (
                "+", "-", "−", "×", "÷", "^", "%",
            ):
                pass
            else:
                self.expression = ""
            self.result_mode = False

        if key == "AC":
            self.expression = ""
            self.history_walk = None

        elif key == "⌫":
            if self.expression in ERROR_MESSAGES:
                self.expression = ""
            else:
                self.expression = self.expression[:-1]

        elif key == "=":
            try:
                original = self.expression or "0"
                result = self.evaluate(original)
                result = self.format_result(result)
                self.history.append((original, result))
                self.trim_history()
                self.refresh_history()
                self.page.run_task(self.save_data)
                self.expression = result
                self.result_mode = True
                # The live answer is already on screen at this point, so let it
                # grow into the display instead of disappearing.
                self.promote_preview()

            except ValueError as e:
                error_msg = str(e)
                self.expression = error_msg
                self.result_mode = True

            except Exception:
                self.expression = "Error"
                self.result_mode = True

        else:
            if self.expression in ERROR_MESSAGES:
                self.expression = ""

            if key == "𝜋":
                self.expression += "pi"
            elif key == "×":
                self.expression += "*"
            elif key == "÷":
                self.expression += "/"
            elif key == "−":
                self.expression += "-"
            elif key == "√":
                self.expression += "sqrt("
            elif key in ("sin", "cos", "tan", "log", "ln"):
                self.expression += key + "("
            else:
                self.expression += key

        self.update_display()

    # ----------------------------
    # The physical keyboard
    # ----------------------------

    def watch_field_focus(self, field: ft.TextField) -> None:
        """Note when a text field takes the caret, and when it lets go.

        A focused field consumes its own printable keys, so a "+" typed into the
        display would otherwise land twice: once as the field's edit and once as a
        pad press. Whatever handlers the field already had are kept and still run.
        """

        already_focused = cast(Callable[[object], None] | None, field.on_focus)
        already_blurred = cast(Callable[[object], None] | None, field.on_blur)

        def note_focus(event) -> None:
            self.text_field_focused = True
            if already_focused is not None:
                already_focused(event)

        def note_blur(event) -> None:
            self.text_field_focused = False
            if already_blurred is not None:
                already_blurred(event)

        field.on_focus = note_focus
        field.on_blur = note_blur

    def handle_keyboard_event(self, event: ft.KeyboardEvent) -> None:
        """Press the pad from a real keyboard: digits, ``+ - * / ( ) % .``, ``^``
        and ``e`` in scientific mode, Enter or ``=`` for ``=``, Backspace for
        ``⌫`` and Escape or Delete for ``AC``.

        Three gates keep the keyboard out of someone else's business. Ctrl/Alt/Meta
        combinations are left to the system. A conversion, currency or pi page has
        no pad to press, and a text field with the caret - the display itself, or
        the value field of the Set Variable dialog - types its own keys. And
        ``pad_key`` returns nothing for a key the pad on screen does not carry, so
        the regular pad never picks up ``^`` or ``e`` from the keyboard any more
        than it does from a tap.
        """

        if event.ctrl or event.alt or event.meta:
            return

        if not self.calculator_showing or self.text_field_focused:
            return

        if event.key in HISTORY_WALK_KEYS:
            self.recall_history(backwards=HISTORY_WALK_KEYS[event.key])
            return

        label = pad_key(event.key, self.scientific, self.memory_keys_on_scientific)
        if label is not None:
            self.handle_key(label)

    def recall_history(self, backwards: bool) -> None:
        """Put a stored calculation back in the display, one arrow press a step.

        The history is kept oldest first and shown newest first, so the walk starts
        at the newest entry and steps back from there; it stops at the oldest
        rather than wrapping, and stepping forward past the newest leaves the
        display empty again, ready for a fresh entry.
        """

        if not self.history:
            return

        if backwards:
            step = (
                0
                if self.history_walk is None
                else min(self.history_walk + 1, len(self.history) - 1)
            )
        elif self.history_walk is None:
            return
        else:
            step = self.history_walk - 1

        if step < 0:
            self.history_walk = None
            self.expression = ""
        else:
            self.history_walk = step
            self.expression = self.history[len(self.history) - 1 - step][0]

        self.result_mode = False
        self.update_display()

    # ----------------------------
    # The calculator memory
    # ----------------------------

    def memory_operand(self) -> Decimal | None:
        """The number the memory keys work on: what the display rests on.

        A live expression is worth what it evaluates to, and a result or a bare
        number is worth itself. An expression that cannot be evaluated - or an
        error message on the display - has no number to store, and comes back as
        None so the press is simply ignored.
        """

        try:
            answer = self.evaluate(self.expression or "0")
            return Decimal(answer)
        except Exception:
            return None

    def press_memory(self, key: str) -> None:
        """One of the memory keys was pressed."""

        if key == "MRC":
            self.recall_memory()
            return

        if key == MEMORY_CLEAR_KEY:
            self.clear_memory()
            return

        value = self.memory_operand()
        if value is None:
            return
        stored = self.memory or Decimal(0)
        self.memory = stored + value if key == "M+" else stored - value
        self.memory_recalled = False
        self.refresh_memory_status()
        self.page.update()

    def clear_memory(self) -> None:
        """MCLR empties the memory, whatever the display is doing.

        A physical calculator's memory-clear key takes the stored number and
        nothing else: the expression, the history and the variables stay.
        """

        self.memory = None
        self.memory_recalled = False
        self.refresh_memory_status()
        self.page.update()

    def leave_memory_mode(self) -> None:
        """The pad swapped its memory row for the variable row, so the memory goes.

        A memory the pad has no keys for cannot be recalled, listed or cleared, so
        it is not left behind the swap. The two rows own each other's state: the
        variable row takes the memory with it, and memory mode puts the variables
        out of use.
        """

        self.memory = None
        self.memory_recalled = False
        self.refresh_memory_status()

    def recall_memory(self) -> None:
        """MRC puts the stored number into the expression; pressing it again clears.

        The second press only counts while nothing else has been pressed since the
        recall, which is what makes one key do both jobs the way a physical
        calculator's MRC does.
        """

        if self.memory_recalled:
            self.memory = None
            self.memory_recalled = False
            self.refresh_memory_status()
            self.page.update()
            return

        if self.memory is None:
            return
        self.memory_recalled = True
        self.press(str(self.memory))

    def refresh_memory_status(self) -> None:
        """Show what the memory holds, the way the variables are listed.

        An empty memory - or one holding zero - shows nothing, which is what a
        physical calculator does with its "M" flag.
        """

        stored = self.memory
        if stored is None or stored == 0:
            self.memory_status.value = ""
            self.memory_status.visible = False
            return

        self.memory_status.value = f"M = {self.format_result(str(stored))}"
        self.memory_status.visible = True

    # ----------------------------
    # Modes, variables, history, conversions
    # ----------------------------

    def set_mode(self, index) -> None:
        self._deactivate_currency_view()
        self.calculator_showing = True
        self.scientific = index == 1
        self.content_area.controls = [self.calculator_view]
        self.expression = ""
        self.result_mode = False
        self.history_walk = None

        self.status.value = (
            "SCIENTIFIC MODE" if self.scientific
            else "REGULAR MODE"
        )
        # The scientific pad without the memory keys runs on its variable keys, and
        # a memory it has no keys for goes with them.
        if self.variables_enabled:
            self.leave_memory_mode()
        self.refresh_variable_status()
        self.reset_preview_slot()

        self.drawer.selected_index = index
        self.rebuild_keypad()
        self.page.update()

    def refresh_variable_status(self) -> None:
        self.variable_status.value = "    ".join(
            f"{name} = {self.variables[name]}"
            for name in VARIABLE_NAMES
            if name in self.variables
        )
        self.variable_status.visible = self.variables_enabled and bool(self.variables)

    @property
    def memory_mode(self) -> bool:
        """Whether the memory keys currently hold the scientific pad's key row.

        That row is the one the named variables live on, so while the memory keys
        are up the pad has no way to set or insert a variable: memory mode.
        """

        return self.scientific and self.memory_keys_on_scientific

    @property
    def variables_enabled(self) -> bool:
        """Whether named variables may be used at all right now.

        Names belong to the Scientific Calculator, and even there only while its
        variable keys are on the pad - see ``memory_mode``.
        """

        return self.scientific and not self.memory_keys_on_scientific

    def variable_context(self) -> dict[str, Decimal]:
        """The variables the engine is allowed to read for this pad."""

        return self.variables if self.variables_enabled else {}

    def used_variable(self, expression: str) -> str | None:
        """A variable name the expression uses, or None if it uses none.

        Only names that actually hold a value count - any other name is an unknown
        name the engine reports itself. Whole words are matched, so a function call
        like ``sqrt`` never reads as the variable ``s``.
        """

        if not self.variables:
            return None
        for token in re.findall(r"[^\W\d_]+", expression):
            if token in self.variables:
                return token
        return None

    def evaluate(self, expression: str) -> str:
        """Calculate with the variables this pad may use.

        In memory mode a name is not arithmetic but a variable the pad has put out
        of reach, so it gets its own message instead of the engine's "Unknown
        constant" - the number is stored, the user just cannot use it here.
        """

        if self.memory_mode and self.used_variable(expression) is not None:
            raise ValueError(ERROR_VARIABLES_DISABLED)
        return calculate(
            expression,
            self.scientific,
            self.degrees,
            self.variable_context(),
        )

    def clear_variables(self, event: object = None) -> None:
        """The "Clear Variables" key: empty every named variable.

        Only the variables go. The expression, the memory and the history are the
        user's and stay where they are; a display already resting on a variable
        re-evaluates and reports what it is worth now.
        """

        del event
        self.variables.clear()
        self.refresh_variable_status()
        self.update_display()
        self.page.update()

    def toggle_angle(self, e) -> None:
        del e
        self.degrees = not self.degrees
        self.angle_label.value = "DEG" if self.degrees else "RAD"
        self.refresh_preview()
        self.page.update()

    def clear_history(self, e) -> None:
        del e
        self.history.clear()
        self.refresh_history()
        self.page.update()
        self.page.run_task(self.save_data)

    def refresh_history(self) -> None:
        """Rebuild the history cards, newest first, capped at the kept items."""

        self.history_list.controls = []
        for equation, answer in reversed(self.history[-self.history_limit:]):
            async def click_equation(e, value=equation):
                del e
                await self.select_history_equation(value)

            async def click_answer(e, value=answer):
                del e
                await self.select_history_answer(value)

            self.history_list.controls.append(
                build_history_card(
                    equation,
                    answer,
                    click_equation,
                    click_answer,
                    self.clipboard.make_button(
                        lambda value=answer: value,
                        tooltip="Copy answer",
                    ),
                )
            )

    async def select_history_equation(self, value) -> None:
        self.expression = value
        self.result_mode = False
        self.update_display()
        await self.page.close_end_drawer()

    async def select_history_answer(self, value) -> None:
        self.expression += value
        self.result_mode = False
        self.update_display()
        await self.page.close_end_drawer()

    def open_conversion(self, conversion) -> None:
        """Swap the calculator for the form of one conversion menu entry."""

        self._deactivate_currency_view()
        group_name = conversion["name"].removesuffix(" Conversion")
        unit_group = self.conversion_groups_by_name.get(group_name)
        if unit_group is None:
            raise ValueError(
                f"No unit group is defined for {conversion['name']}"
            )

        units = unit_group["units"]
        if not units:
            raise ValueError(f"No units are defined for {group_name}")

        # The view owns the live conversion handler; keeping the view on the app
        # keeps the handlers its controls hold alive with it.
        self.conversion_view = ConversionView(
            self.page,
            conversion,
            units,
            self.conversion_unit_labels,
            self.clipboard.make_button,
        )
        self.content_area.controls = [self.conversion_view.build()]
        self.calculator_showing = False
        self.status.value = "UNIT CONVERSION"
        self.page.update()

    def open_currency_conversion(self) -> None:
        """Swap the calculator for the live currency conversion form."""

        self._deactivate_currency_view()
        self.currency_view = CurrencyConversionView(
            self.page,
            self.clipboard.make_button,
        )
        self.content_area.controls = [self.currency_view.build()]
        self.calculator_showing = False
        self.status.value = "CURRENCY CONVERSION"
        self.page.update()
        self.page.run_task(self.currency_view.load_currencies)

    def _deactivate_currency_view(self) -> None:
        if self.currency_view is not None:
            self.currency_view.deactivate()
            self.currency_view = None

    def open_pi(self) -> None:
        """Swap the calculator for the pi calculation page."""

        self._deactivate_currency_view()
        # The view is kept on the app for the same reason the conversion view is:
        # the handlers its controls hold are methods of it.
        if self.pi_view is None:
            self.pi_view = PiView(
                self.page,
                self.clipboard.make_button,
                on_program_pi_changed=self.persist_pi_change,
            )
        self.conversion_view = None
        self.content_area.controls = [self.pi_view.build()]
        self.calculator_showing = False
        self.status.value = "PI CALCULATION"
        self.page.update()
