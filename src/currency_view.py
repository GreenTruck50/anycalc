"""Live currency conversion form backed by the daily exchange-rate API."""

import asyncio
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any, Callable, Protocol

import flet as ft

from config import ERROR_INVALID_NUMBER, ERROR_NUMBER_OVERFLOW
from conversions import format_conversion_value
from currency_api import CurrencyApi, CurrencyApiError, CurrencyRates
from styles import ACCENT, TEXT_FAINT, TEXT_MUTED


class _Page(Protocol):
    def update(self) -> None: ...


class CurrencyConversionView:
    """The live amount-and-currency form."""

    def __init__(
        self,
        page: _Page,
        make_copy_button: Callable[..., ft.Control],
        api: CurrencyApi | None = None,
    ) -> None:
        self.page = page
        self.make_copy_button = make_copy_button
        self.api = api or CurrencyApi()
        self.active = True
        self.request_token = 0
        self.currency_options: dict[str, str] = {}

    def build(self) -> ft.Column:
        self.input_field = ft.TextField(
            key="currency-value",
            label="Value",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            on_change=self.run_conversion,
        )
        self.result_field = ft.TextField(
            key="currency-result",
            label="Result",
            read_only=True,
        )
        self.result_field.suffix = self.make_copy_button(
            lambda: self.result_field.value,
            tooltip="Copy converted value",
        )
        self.source_dropdown = ft.Dropdown(
            key="currency-from",
            label="From",
            options=[],
            on_select=self.run_conversion,
            expand=True,
        )
        self.target_dropdown = ft.Dropdown(
            key="currency-to",
            label="To",
            options=[],
            on_select=self.run_conversion,
            expand=True,
        )
        self.status = ft.Text(
            "Loading available currencies…",
            size=11,
            color=TEXT_MUTED,
            key="currency-status",
        )
        self.rate_date = ft.Text(
            "",
            size=11,
            color=TEXT_FAINT,
            key="currency-rate-date",
            visible=False,
        )
        self.retry_button = ft.TextButton(
            "Retry",
            key="currency-retry",
            on_click=self.load_currencies,
            visible=False,
        )
        self.swap_button = ft.OutlinedButton(
            key="currency-swap",
            content="Swap currencies",
            icon=ft.Icons.SWAP_HORIZ,
            icon_color=ACCENT,
            tooltip="Swap the From and To currencies",
            on_click=self.swap_currencies,
        )

        def stretched(dropdown: ft.Dropdown) -> ft.Row:
            return ft.Row([dropdown])

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CURRENCY_EXCHANGE, size=28, color=ACCENT),
                        ft.Text(
                            "Currency Conversion",
                            size=22,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Text(
                    "Convert using daily exchange rates, including supported "
                    "cryptocurrencies and metals.",
                    color=TEXT_MUTED,
                ),
                self.input_field,
                stretched(self.source_dropdown),
                self.swap_button,
                stretched(self.target_dropdown),
                ft.Row([self.status, self.retry_button], spacing=8),
                self.rate_date,
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SWAP_HORIZ, size=16, color=TEXT_FAINT),
                        ft.Text(
                            "Converts as you type or change currencies",
                            size=11,
                            color=TEXT_FAINT,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.result_field,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    async def load_currencies(self, e: Any = None) -> None:
        del e
        if not self.active:
            return
        self.status.value = "Loading available currencies…"
        self.status.color = TEXT_MUTED
        self.retry_button.visible = False
        self.page.update()
        try:
            currencies = await asyncio.to_thread(self.api.get_currencies)
        except CurrencyApiError as error:
            if self.active:
                self.status.value = str(error)
                self.status.color = ft.Colors.RED_400
                self.retry_button.visible = True
                self.page.update()
            return

        if not self.active:
            return
        self.currency_options = currencies
        options = [
            ft.DropdownOption(
                key=code,
                text=f"{name} ({code.upper()})",
            )
            for code, name in sorted(
                currencies.items(),
                key=lambda item: item[1].casefold(),
            )
        ]
        self.source_dropdown.options = options
        self.target_dropdown.options = options
        self.source_dropdown.value = "usd" if "usd" in currencies else options[0].key
        self.target_dropdown.value = (
            "eur"
            if "eur" in currencies
            else next(
                (option.key for option in options if option.key != self.source_dropdown.value),
                self.source_dropdown.value,
            )
        )
        self.status.value = f"{len(currencies)} currencies available."
        self.status.color = TEXT_MUTED
        self.page.update()
        await self.run_conversion()

    async def run_conversion(self, e: Any = None) -> None:
        del e
        self.request_token += 1
        token = self.request_token
        self.result_field.error = None
        self.result_field.value = ""
        self.rate_date.value = ""
        self.rate_date.visible = False

        raw_amount = (self.input_field.value or "").strip()
        if not raw_amount:
            self.page.update()
            return
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            self.page.update()
            return
        if not amount.is_finite():
            self.result_field.error = ERROR_INVALID_NUMBER
            self.page.update()
            return

        source = self.source_dropdown.value
        target = self.target_dropdown.value
        if source is None or target is None:
            self.page.update()
            return
        if source == target:
            try:
                self.result_field.value = format_conversion_value(amount)
            except DecimalException:
                self.result_field.error = ERROR_NUMBER_OVERFLOW
            self.page.update()
            return

        self.status.value = "Loading exchange rate…"
        self.status.color = TEXT_MUTED
        self.page.update()
        try:
            rates: CurrencyRates = await asyncio.to_thread(
                self.api.get_rates,
                source,
            )
        except CurrencyApiError as error:
            if self.active and token == self.request_token:
                self.result_field.error = str(error)
                self.status.value = ""
                self.page.update()
            return

        if not self.active or token != self.request_token:
            return
        rate = rates.rates.get(target)
        if rate is None:
            self.result_field.error = (
                f"No {source.upper()} to {target.upper()} rate is available."
            )
            self.status.value = ""
        else:
            try:
                self.result_field.value = format_conversion_value(amount * rate)
            except DecimalException:
                self.result_field.error = ERROR_NUMBER_OVERFLOW
                self.status.value = ""
            else:
                self.status.value = ""
                self.rate_date.value = f"Rate date: {rates.date}"
                self.rate_date.visible = True
        self.page.update()

    async def swap_currencies(self, e: Any) -> None:
        self.source_dropdown.value, self.target_dropdown.value = (
            self.target_dropdown.value,
            self.source_dropdown.value,
        )
        await self.run_conversion(e)

    def deactivate(self) -> None:
        self.active = False
        self.request_token += 1
