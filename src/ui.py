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
from decimal import Decimal

import flet as ft

from calculate import calculate, is_number, toggle_sign
from clipboard import ClipboardService
from config import (
    DISPLAY_TEXT_COLOR,
    DISPLAY_TEXT_SIZE,
    ERROR_MESSAGES,
    MAX_HISTORY_ITEMS,
    PREVIEW_MORPH_LIFT,
    PREVIEW_MORPH_MS,
    PREVIEW_TEXT_COLOR,
    PREVIEW_TEXT_SIZE,
    VARIABLE_NAMES,
)
from conversion_view import ConversionView
from conversions import load_conversion_config
from history_view import build_history_card, build_history_drawer
from keypad import (
    DIALOG_KEYS,
    REGULAR_ROWS,
    SCIENTIFIC_ROWS,
    key_color,
    make_key,
)
import pi_value
from pi_view import PiView
from styles import (
    APP_BACKGROUND,
    KEY_OPERATOR,
    PANEL_BACKGROUND,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from variable_dialogs import open_insert_variable_dialog, open_set_variable_dialog


class AnycalcApp:
    """The AnythingCalculator window: two calculator pads and the conversions."""

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

        # The conversion form currently in the content area, if any.
        self.conversion_view: ConversionView | None = None

        # The pi page, built the first time it is opened.
        self.pi_view: PiView | None = None

        # The pi every calculation in the app multiplies by is computed here, once,
        # before anything is on screen: the app starts on its own 12-decimal pi
        # rather than on the 15-decimal float math.pi, and the Pi page can replace
        # it with a longer one at any time.
        self.program_pi_run = pi_value.install_default_pi()

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
        page.title = "AnythingCalculator"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = APP_BACKGROUND
        page.padding = 16

        # Mobile renders edge-to-edge, so the system bars are given the page colour
        # and light icons instead of floating over the app in their own colours. The
        # bars stay visible; the content that used to sit under them is pushed clear
        # by the SafeArea the page is built inside (see the bottom of this method).
        page.theme = ft.Theme(
            system_overlay_style=ft.SystemOverlayStyle(
                status_bar_color=APP_BACKGROUND,
                status_bar_brightness=ft.Brightness.DARK,
                status_bar_icon_brightness=ft.Brightness.LIGHT,
                system_navigation_bar_color=APP_BACKGROUND,
                system_navigation_bar_divider_color=APP_BACKGROUND,
                system_navigation_bar_icon_brightness=ft.Brightness.LIGHT,
            )
        )

        page.window.width = 400
        page.window.height = 780
        page.window.min_width = 320
        page.window.min_height = 500

        self._build_display()

        self.status = ft.Text("REGULAR MODE", size=12, color=TEXT_MUTED)
        self.variable_status = ft.Text(
            "",
            size=11,
            color=TEXT_MUTED,
            visible=False,
        )
        self.history_list = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
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

    def _build_display(self) -> None:
        """The caption above the display, the display field, its copy button and
        the live answer's slot underneath."""

        self.expression_label = ft.Text(
            "EXPRESSION",
            size=11,
            color=TEXT_MUTED,
        )

        self.display = ft.TextField(
            # key: stable handle for the integration tests in tests/ (see the Flet
            # integration-testing docs) - it has no effect on what the user sees.
            key="display",
            value="0",
            text_size=DISPLAY_TEXT_SIZE,
            color=TEXT_PRIMARY,
            text_align=ft.TextAlign.RIGHT,
            border=ft.NoInputBorder(),
            content_padding=0,
            expand=True,
            on_change=lambda e: self.handle_display_change(e.control.value),
            on_focus=lambda e: self.select_result(e.control),
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
            color=PREVIEW_TEXT_COLOR,
            text_align=ft.TextAlign.RIGHT,
            animate_size=ft.AnimationStyle(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
        )
        self.preview_slot = ft.Container(
            content=self.preview_value,
            alignment=ft.Alignment.CENTER_RIGHT,
            animate_size=ft.AnimationStyle(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
            animate_offset=ft.AnimationStyle(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
            animate_opacity=ft.AnimationStyle(
                duration=PREVIEW_MORPH_MS,
                curve=ft.AnimationCurve.EASE_IN,
            ),
            visible=False,
        )

    def _build_header(self) -> None:
        """Menu button, the title with its mode caption, and the history button."""

        self.header = ft.Row(
            [
                ft.IconButton(
                    key="menu-button",
                    icon=ft.Icons.MENU,
                    icon_color=TEXT_PRIMARY,
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
                    icon=ft.Icons.HISTORY,
                    icon_color=TEXT_PRIMARY,
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
                    self.variable_status,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            bgcolor=PANEL_BACKGROUND,
            border_radius=18,
            padding=16,
            height=168,
        )

    def _build_history_drawer(self) -> None:
        """The end drawer with the calculation history."""

        page = self.page
        page.end_drawer = build_history_drawer(
            self.history_list,
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
                                color=TEXT_MUTED,
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
                        color=TEXT_MUTED,
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
                        color=TEXT_MUTED,
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
                        "Other",
                        size=12,
                        color=TEXT_MUTED,
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
        else:
            self.open_pi()

    async def open_menu(self, e) -> None:
        del e
        await self.page.show_drawer()

    async def open_history(self, e) -> None:
        del e
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
            answer = calculate(
                self.expression,
                self.scientific,
                self.degrees,
                self.variables,
            )
        except Exception:
            return ""

        # A bare number is already the answer; showing it twice is noise.
        return "" if answer == self.expression else answer

    def reset_preview_slot(self) -> None:
        """Put the preview back at its small resting state, hidden."""
        self.preview_morphing = False
        self.preview_value.size = PREVIEW_TEXT_SIZE
        self.preview_value.color = PREVIEW_TEXT_COLOR
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
        self.preview_value.color = DISPLAY_TEXT_COLOR
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
        """Put the pad's rows back: the scientific rows on top when in that mode."""

        self.keypad.controls.clear()

        if self.scientific:
            for row in SCIENTIFIC_ROWS:
                self.keypad.controls.append(
                    ft.Row(
                        [
                            make_key(key, self.handle_key, KEY_OPERATOR)
                            for key in row
                        ],
                        spacing=8,
                    )
                )

        for row in REGULAR_ROWS:
            self.keypad.controls.append(
                ft.Row(
                    [make_key(key, self.handle_key, key_color(key)) for key in row],
                    spacing=8,
                )
            )

        self.page.update()

    def handle_key(self, label: str) -> None:
        """Dispatch a key press: the two variable keys open dialogs, the rest press."""

        if label not in DIALOG_KEYS:
            self.press(label)
            return

        if label == "Set Variable":
            open_set_variable_dialog(self)
        else:
            open_insert_variable_dialog(self)

    def press(self, key):
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

        elif key == "⌫":
            if self.expression in ERROR_MESSAGES:
                self.expression = ""
            else:
                self.expression = self.expression[:-1]

        elif key == "=":
            try:
                original = self.expression or "0"
                result = calculate(
                    original,
                    self.scientific,
                    self.degrees,
                    self.variables,
                )
                self.history.append((original, result))
                self.refresh_history()
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
    # Modes, variables, history, conversions
    # ----------------------------

    def set_mode(self, index) -> None:
        self.scientific = index == 1
        self.content_area.controls = [self.calculator_view]
        self.expression = ""
        self.result_mode = False

        self.status.value = (
            "SCIENTIFIC MODE" if self.scientific
            else "REGULAR MODE"
        )
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
        self.variable_status.visible = self.scientific and bool(self.variables)

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

    def refresh_history(self) -> None:
        """Rebuild the history cards, newest first, capped at the kept items."""

        self.history_list.controls = []
        for equation, answer in reversed(self.history[-MAX_HISTORY_ITEMS:]):
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
        self.status.value = "UNIT CONVERSION"
        self.page.update()

    def open_pi(self) -> None:
        """Swap the calculator for the pi calculation page."""

        # The view is kept on the app for the same reason the conversion view is:
        # the handlers its controls hold are methods of it.
        if self.pi_view is None:
            self.pi_view = PiView(self.page, self.clipboard.make_button)
        self.conversion_view = None
        self.content_area.controls = [self.pi_view.build()]
        self.status.value = "PI CALCULATION"
        self.page.update()
