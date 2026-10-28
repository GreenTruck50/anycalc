"""The unit conversion page: value, two units, a swap button, live result, chain
of operations.

One instance builds the form for a single conversion menu entry from
``src/assets/conversions.yaml``. Conversions run live - every change of the value
or of either unit re-runs them, so there is no Convert button - and the chain
under the result shows every hop the engine took, with the formula it applied.

The view owns nothing but its own controls; the app decides when the form goes
into the content area.
"""

from decimal import Decimal, DivisionByZero, InvalidOperation, Overflow
from typing import Any, Callable

import flet as ft

from conversions import (
    ConversionStep,
    convert_units,
    format_conversion_value,
)
from styles import ACCENT, CARD_BACKGROUND, TEXT_FAINT, TEXT_MUTED, TEXT_SOFT


class ConversionView:
    """The conversion form for one menu entry.

    :param page: the page the form is shown on (only used to update it).
    :param conversion: the menu entry - name, description, icon, formulas.
    :param units: the unit group this entry converts between.
    :param unit_labels: unit id -> "Name (symbol)", for the chain cards.
    :param make_copy_button: the app's shared copy-button factory.
    """

    def __init__(
        self,
        page: ft.Page,
        conversion: dict[str, Any],
        units: list[dict[str, str]],
        unit_labels: dict[str, str],
        make_copy_button: Callable[..., ft.IconButton],
    ) -> None:
        self.page = page
        self.conversion = conversion
        self.units = units
        self.unit_labels = unit_labels
        self.make_copy_button = make_copy_button

    def build(self) -> ft.Column:
        """Assemble the form.

        The handler below reads the fields defined after it - they only have to
        exist by the time a handler runs.
        """

        def run_conversion(e) -> None:
            del e
            self.input_field.error = None
            self.result_field.error = None
            self.result_field.value = ""
            self.clear_chain()
            # The notes follow the units, not the number, so they are refreshed
            # before the empty-value and half-typed-value early returns below.
            self.refresh_guidance()

            input_text = (self.input_field.value or "").strip()
            if not input_text:
                self.page.update()
                return

            try:
                input_value = Decimal(input_text)
            except InvalidOperation:
                # Half-typed values ("-", "3.", "abc") are part of typing a
                # number, so they clear the result instead of reporting noise.
                self.page.update()
                return

            try:
                outcome = convert_units(
                    self.conversion,
                    input_value,
                    self.source_dropdown.value,
                    self.target_dropdown.value,
                )
            except (ValueError, DivisionByZero, Overflow) as error:
                self.result_field.error = str(error)
            else:
                self.result_field.value = format_conversion_value(outcome.value)
                self.show_chain(outcome.steps)
            self.page.update()

        self.input_field = ft.TextField(
            key="conversion-value",
            label="Value",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            on_change=run_conversion,
        )
        self.result_field = ft.TextField(
            key="conversion-result",
            label="Result",
            read_only=True,
        )
        self.result_field.suffix = self.make_copy_button(
            lambda: self.result_field.value,
            tooltip="Copy converted value",
        )
        unit_options = [
            ft.DropdownOption(
                key=unit["id"],
                text=f"{unit['name']} ({unit['symbol']})",
            )
            for unit in self.units
        ]
        # Both dropdowns re-convert live: they point at the handler defined
        # above, because an on_select handler is looked up when the control is
        # built.
        #
        # A Flutter DropdownMenu sizes its own box to its widest option and
        # ignores the width its parent offers it, unless `expandedInsets` is set
        # - which Flet only sends when the control has `expand` (dropdown.dart:
        # expandedInsets = expand > 0 ? getPadding("expanded_insets", zero) :
        # null). `expand` inside a Column would stretch it vertically, so each
        # dropdown goes into a Row of its own, where `expand` is the horizontal
        # axis and the Row already spans the page. With that the box matches the
        # value and result fields at any window width instead of stopping short
        # at the length of its longest unit name.
        self.source_dropdown = ft.Dropdown(
            key="conversion-from",
            label="From",
            value=self.units[0]["id"],
            options=unit_options,
            on_select=run_conversion,
            expand=True,
        )
        self.target_dropdown = ft.Dropdown(
            key="conversion-to",
            label="To",
            value=self.units[1]["id"] if len(self.units) > 1 else self.units[0]["id"],
            options=unit_options,
            on_select=run_conversion,
            expand=True,
        )

        def stretched(dropdown: ft.Dropdown) -> ft.Row:
            """Wrap a dropdown so the page's stretch reaches its painted box."""

            return ft.Row([dropdown])

        # The two selected units' notes about where that unit is actually used -
        # a US cup is not an Australian cup, a US tablespoon is not an Australian
        # one. Shown only for units that carry a guidance line in the YAML.
        self.units_by_id = {unit["id"]: unit for unit in self.units}
        self.guidance_lines = ft.Column(
            [],
            key="conversion-guidance",
            spacing=4,
            visible=False,
        )

        def swap_units(e) -> None:
            """Turn the conversion around and re-run it on the typed value."""

            self.source_dropdown.value, self.target_dropdown.value = (
                self.target_dropdown.value,
                self.source_dropdown.value,
            )
            # run_conversion clears its own event argument; this one is passed on.
            run_conversion(e)

        self.swap_button = ft.OutlinedButton(
            key="conversion-swap",
            content="Swap units",
            icon=ft.Icons.SWAP_HORIZ,
            icon_color=ACCENT,
            tooltip="Swap the From and To units",
            on_click=swap_units,
        )

        self.chain_header = ft.Text("CHAIN OF OPERATIONS", size=10, color=TEXT_MUTED)
        self.chain_list = ft.Column(
            [],
            spacing=8,
            key="conversion-chain",
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.chain_view = ft.Column(
            [self.chain_header, self.chain_list],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            visible=False,
        )

        icon_name = self.conversion["icon"].rsplit(".", 1)[-1]
        icon = getattr(ft.Icons, icon_name)
        # The page opens already showing the notes for the units it opens on.
        self.refresh_guidance()
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(icon, size=28, color=ACCENT),
                        ft.Text(
                            self.conversion["name"],
                            size=22,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Text(self.conversion["description"], color=TEXT_MUTED),
                self.input_field,
                stretched(self.source_dropdown),
                self.swap_button,
                stretched(self.target_dropdown),
                self.guidance_lines,
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SWAP_HORIZ,
                            size=16,
                            color=TEXT_FAINT,
                        ),
                        ft.Text(
                            "Converts as you type or change units",
                            size=11,
                            color=TEXT_FAINT,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.result_field,
                self.chain_view,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            # Everything on the page - fields, dropdowns, the swap button, the chain
            # cards - takes the width of the content area rather than sizing itself to
            # its caption, the way the history cards in the drawer do.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def clear_chain(self) -> None:
        self.chain_list.controls = []
        self.chain_view.visible = False

    def refresh_guidance(self) -> None:
        """Note, for each selected unit, where that unit is the one to reach for.

        A recipe's "cup" or "tablespoon" is a different volume depending on the
        country it was written for, so the YAML carries a note per unit and the
        page shows the notes of the two units currently selected. Units without a
        note - the metric cubic units, most of the weight group - add nothing.
        """

        notes: list[ft.Control] = []
        seen: set[str] = set()
        for unit_id in (self.source_dropdown.value, self.target_dropdown.value):
            guidance = self.units_by_id.get(unit_id, {}).get("guidance")
            if not guidance or guidance in seen:
                continue
            seen.add(guidance)
            label = self.unit_labels.get(unit_id, unit_id)
            notes.append(ft.Text(f"{label}: {guidance}", size=11, color=TEXT_SOFT))
        if notes:
            notes.insert(0, ft.Text("UNIT GUIDANCE", size=10, color=TEXT_MUTED))
        self.guidance_lines.controls = notes
        self.guidance_lines.visible = bool(notes)

    def chain_card(self, lines: list[ft.Control]) -> ft.Container:
        return ft.Container(
            content=ft.Column(lines, spacing=4),
            bgcolor=CARD_BACKGROUND,
            border_radius=8,
            padding=10,
        )

    def chain_step_card(self, index: int, step: ConversionStep) -> ft.Container:
        """One hop: the units, the values, and the formula behind a button.

        A hop that reused a formula backwards shows that formula already
        flipped, so the formula on screen is the one that was applied.
        """
        source_label = self.unit_labels.get(step.from_unit_id, step.from_unit_id)
        target_label = self.unit_labels.get(step.to_unit_id, step.to_unit_id)
        formula_line = ft.Text(
            step.applied_formula,
            size=12,
            color=TEXT_SOFT,
            visible=False,
        )

        def toggle_formula(e):
            del e
            formula_line.visible = not formula_line.visible
            view_formula_button.content = (
                "Hide formula" if formula_line.visible else "View formula"
            )
            self.page.update()

        # Defined after the handler above on purpose: the handler only reads
        # this name when it runs, which is always after the button exists.
        view_formula_button = ft.TextButton(
            content="View formula",
            tooltip="Show the formula applied for this step",
            on_click=toggle_formula,
        )
        return self.chain_card(
            [
                ft.Row(
                    [
                        ft.Text(
                            f"{index}. {source_label} → {target_label}",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        view_formula_button,
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    f"{format_conversion_value(step.input_value)} → "
                    f"{format_conversion_value(step.output_value)}",
                    size=12,
                    color=TEXT_MUTED,
                ),
                formula_line,
            ]
        )

    def show_chain(self, steps: list[ConversionStep]) -> None:
        self.chain_list.controls = []
        if not steps:
            self.chain_list.controls.append(
                self.chain_card(
                    [
                        ft.Text(
                            "Same unit - the value is passed through unchanged.",
                            size=12,
                            color=TEXT_MUTED,
                        )
                    ]
                )
            )
        else:
            self.chain_list.controls.extend(
                self.chain_step_card(index, step)
                for index, step in enumerate(steps, start=1)
            )
        self.chain_header.value = (
            f"CHAIN OF OPERATIONS ({len(steps)} step{'s' if len(steps) != 1 else ''})"
        )
        self.chain_view.visible = True
