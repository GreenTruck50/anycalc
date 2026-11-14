"""Live currency conversion form backed by the daily exchange-rate API."""

import asyncio
from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any, Callable, Protocol

import flet as ft

from config import ERROR_INVALID_NUMBER, ERROR_NUMBER_OVERFLOW
from conversions import format_conversion_value
from currency_api import (
    CurrencyApi,
    CurrencyApiError,
    CurrencyRates,
    SavedCurrencyRates,
    as_saved_currency_rates,
    rate_age_in_days,
    rates_from_saved,
)
from dropdowns import searchable
import styles


class _Page(Protocol):
    def update(self) -> None: ...


# The colour the page goes to when the numbers on screen are not today's - a
# warning that is not an error, so it is neither the theme's muted text nor its
# error red. Amber reads on both the light and the dark themes, and the chip's
# fill and border are the same amber at partial opacity over whatever the theme's
# background happens to be.
STALENESS_TEXT = "#F59E0B"
STALENESS_FILL = ft.Colors.with_opacity(0.14, STALENESS_TEXT)
STALENESS_EDGE = ft.Colors.with_opacity(0.45, STALENESS_TEXT)


class CurrencyConversionView:
    """The live amount-and-currency form.

    :param page: the page the form is shown on (only used to update it).
    :param make_copy_button: the app's shared copy-button factory.
    :param api: the exchange-rate client, swappable for tests.
    :param saved_pair: the (from, to) currency codes the user last chose, if the
        app remembers them. A code the API no longer offers is ignored.
    :param on_pair_changed: called with the two codes whenever the pair on screen
        changes, so the app can remember it.
    :param saved_currencies: the currency list the API served the last time it
        was reached, used only when neither host answers now.
    :param saved_rates: the rate table from that same run, used the same way.
    :param on_currencies_loaded: called with a currency list the API just served,
        so the app can keep it. Never called for a saved one.
    :param on_rates_saved: called with the storable form of a rate table the API
        just served, so the app can keep it. Never called for a saved one, which
        is what stops an offline session from ageing the stored rates.
    :param today: what the staleness badge counts from. A parameter rather than a
        call to ``date.today`` so a test can hold the clock still.
    """

    def __init__(
        self,
        page: _Page,
        make_copy_button: Callable[..., ft.Control],
        api: CurrencyApi | None = None,
        saved_pair: tuple[str, str] | None = None,
        on_pair_changed: Callable[[str, str], None] | None = None,
        saved_currencies: dict[str, str] | None = None,
        saved_rates: SavedCurrencyRates | None = None,
        on_currencies_loaded: Callable[[dict[str, str]], None] | None = None,
        on_rates_saved: Callable[[SavedCurrencyRates], None] | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.page = page
        self.make_copy_button = make_copy_button
        self.api = api or CurrencyApi()
        self.saved_pair = saved_pair
        self.on_pair_changed = on_pair_changed
        self.saved_currencies = saved_currencies
        self.saved_rates = saved_rates
        self.on_currencies_loaded = on_currencies_loaded
        self.on_rates_saved = on_rates_saved
        self.today = today
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
        # The rate table carries hundreds of codes, so these boxes are searchable
        # like the unit boxes are (see dropdowns.py).
        self.source_dropdown = searchable(
            ft.Dropdown(
                key="currency-from",
                label="From",
                options=[],
                on_select=self.select_currency,
                expand=True,
            ),
            self.page,
            search_icon=True,
        )
        self.target_dropdown = searchable(
            ft.Dropdown(
                key="currency-to",
                label="To",
                options=[],
                on_select=self.select_currency,
                expand=True,
            ),
            self.page,
            search_icon=True,
        )
        self.status = ft.Text(
            "Loading available currencies…",
            size=11,
            color=styles.TEXT_MUTED,
            key="currency-status",
        )
        self.rate_date = ft.Text(
            "",
            size=11,
            color=styles.TEXT_FAINT,
            key="currency-rate-date",
            visible=False,
        )
        # The badge that says the rates on screen are not today's: how many days
        # old they are, that they came off the disk rather than off the network,
        # or both. Hidden whenever the numbers are current.
        self.staleness_text = ft.Text(
            "",
            size=10,
            weight=ft.FontWeight.BOLD,
            color=STALENESS_TEXT,
        )
        self.staleness = ft.Container(
            key="currency-staleness",
            content=self.staleness_text,
            bgcolor=STALENESS_FILL,
            border=ft.Border.all(1, STALENESS_EDGE),
            border_radius=999,
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
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
            icon_color=styles.ACCENT,
            tooltip="Swap the From and To currencies",
            on_click=self.swap_currencies,
        )

        def stretched(dropdown: ft.Dropdown) -> ft.Row:
            return ft.Row([dropdown])

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CURRENCY_EXCHANGE, size=28, color=styles.ACCENT),
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
                    color=styles.TEXT_MUTED,
                ),
                self.input_field,
                stretched(self.source_dropdown),
                self.swap_button,
                stretched(self.target_dropdown),
                ft.Row([self.status, self.retry_button], spacing=8),
                ft.Row(
                    [self.rate_date, self.staleness],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SWAP_HORIZ, size=16, color=styles.TEXT_FAINT),
                        ft.Text(
                            "Converts as you type or change currencies",
                            size=11,
                            color=styles.TEXT_FAINT,
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

    def opening_pair(
        self, currencies: dict[str, str], options: list[ft.DropdownOption]
    ) -> tuple[str, str]:
        """Which two currencies the form starts on.

        The pair the app remembered wins, but only while the API still offers both
        codes: a currency that has dropped out must not leave a dropdown showing a
        value its own option list does not contain. With no usable saved pair the
        form opens on US dollar to euro, the pair most people want first.
        """

        if self.saved_pair is not None:
            source, target = self.saved_pair
            if source in currencies and target in currencies:
                return source, target
        # A DropdownOption's key is optional in Flet's own types, so the codes are
        # narrowed to the real ones before either dropdown is set.
        codes = [code for code in (option.key for option in options) if code]
        source = "usd" if "usd" in currencies else (codes[0] if codes else "")
        target = (
            "eur"
            if "eur" in currencies
            else next((code for code in codes if code != source), source)
        )
        return source, target

    def remember_pair(self) -> None:
        """Offer the pair now on screen to the app, if it wants to remember it."""

        if self.on_pair_changed is None:
            return
        source = self.source_dropdown.value
        target = self.target_dropdown.value
        if source is not None and target is not None:
            self.on_pair_changed(source, target)

    async def select_currency(self, e: Any = None) -> None:
        """A currency picked from a dropdown: remember the new pair, re-convert.

        This has to stay a coroutine: the page awaits an async ``on_select``
        handler, and a plain wrapper around ``run_conversion`` would leave its
        coroutine unscheduled.
        """

        self.remember_pair()
        await self.run_conversion(e)

    async def load_currencies(self, e: Any = None) -> None:
        del e
        if not self.active:
            return
        self.status.value = "Loading available currencies…"
        self.status.color = styles.TEXT_MUTED
        self.retry_button.visible = False
        self.page.update()
        from_save = False
        try:
            currencies = await asyncio.to_thread(self.api.get_currencies)
        except CurrencyApiError as error:
            if self.saved_currencies is None:
                if self.active:
                    self.status.value = str(error)
                    self.status.color = ft.Colors.RED_400
                    self.retry_button.visible = True
                    self.page.update()
                return
            # Neither host answered, but the one that did last time left a list
            # behind. The page is usable on it; the amber says it is not live.
            currencies = self.saved_currencies
            from_save = True

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
        self.source_dropdown.value, self.target_dropdown.value = self.opening_pair(
            currencies, options
        )
        if from_save:
            self.status.value = (
                f"{len(currencies)} currencies from the last saved list."
            )
            self.status.color = STALENESS_TEXT
            # Worth another try: the network may well be back by the next tap.
            self.retry_button.visible = True
        else:
            self.status.value = f"{len(currencies)} currencies available."
            self.status.color = styles.TEXT_MUTED
            if self.on_currencies_loaded is not None:
                self.on_currencies_loaded(currencies)
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
        self.staleness.visible = False

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
        self.status.color = styles.TEXT_MUTED
        self.page.update()
        try:
            rates: CurrencyRates = await asyncio.to_thread(
                self.api.get_rates,
                source,
            )
            from_save = False
        except CurrencyApiError as error:
            if self.saved_rates is None:
                if self.active and token == self.request_token:
                    self.result_field.error = str(error)
                    self.status.value = ""
                    self.page.update()
                return
            # The network is down, so the last table the app saw gets a turn. Its
            # own error is what gets reported when it cannot price this pair
            # either - that is the reason the user can act on.
            try:
                rates = rates_from_saved(self.saved_rates, source)
            except CurrencyApiError as saved_error:
                if self.active and token == self.request_token:
                    self.result_field.error = str(saved_error)
                    self.status.value = ""
                    self.page.update()
                return
            from_save = True

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
                if from_save:
                    self.status.value = (
                        "Live rates are unavailable - converting with the last "
                        "saved rates."
                    )
                    self.status.color = STALENESS_TEXT
                else:
                    self.status.value = ""
                    self.status.color = styles.TEXT_MUTED
                    if self.on_rates_saved is not None:
                        self.on_rates_saved(as_saved_currency_rates(source, rates))
                self.rate_date.value = f"Rates as of {rates.date}"
                self.rate_date.visible = True
                label = self.staleness_label(rates, from_save)
                self.staleness_text.value = label or ""
                self.staleness.visible = label is not None
        self.page.update()

    def staleness_label(self, rates: CurrencyRates, from_save: bool) -> str | None:
        """What the staleness badge has to say, or None when it has nothing to say.

        Nothing to say means the numbers on screen are today's and came off the
        network. Otherwise the badge says how old they are, that they came out of
        client storage rather than off the network, or both.
        """

        age = rate_age_in_days(rates.date, self.today())
        parts: list[str] = []
        if from_save:
            parts.append("Last known")
        if age >= 1:
            parts.append(f"{age} day old" if age == 1 else f"{age} days old")
        if not parts:
            return None
        return " — ".join(parts)

    async def swap_currencies(self, e: Any) -> None:
        self.source_dropdown.value, self.target_dropdown.value = (
            self.target_dropdown.value,
            self.source_dropdown.value,
        )
        # A swap is a choice of pair like any other, so it is remembered too.
        self.remember_pair()
        await self.run_conversion(e)

    def deactivate(self) -> None:
        self.active = False
        self.request_token += 1
