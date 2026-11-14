"""The exchange data the app keeps so the currency page survives an outage.

The currency page asks the exchange API for a currency list and a rate table.
Whatever a live run served is handed back to the app, which keeps it in client
storage; the next run - or the next hour with no network - converts with it and
says so on screen. No app host is needed: the app is built over the shared page
stub in ``tests/stub_page.py``, and its page is driven with a stubbed client. Run
this file with ``pytest -k currency``.

Who owns what, and why the checks sit where they do:

* the view decides when the kept data is used, because only it knows the live
  fetch just failed;
* the app decides what is kept, because a view owns no storage - and it is only
  ever offered live data, which is what stops an offline session from ageing the
  save;
* the storage layer only vouches for the shape, which is what
  ``tests/test_data_storage.py`` checks.
"""

import asyncio
from decimal import Decimal
from typing import Any

from currency_api import CurrencyApiError, CurrencyRates, SavedCurrencyRates
from data_storage import AppState
from stub_page import build_app


class StubStore:
    """A client storage that returns one prepared state and stores nothing else."""

    def __init__(self, state: AppState) -> None:
        self.state = state

    async def load(self) -> AppState:
        return self.state

    async def save(self, state: AppState, include_pi: bool = False) -> None:
        del state, include_pi

    async def clear(self) -> None:
        pass


class StubApi:
    """An exchange client that either serves the data or is simply not there."""

    def __init__(
        self,
        currencies: dict[str, str] | None = None,
        rates: dict[str, Decimal] | None = None,
    ) -> None:
        self.currencies = currencies
        self.rates = rates

    def get_currencies(self) -> dict[str, str]:
        if self.currencies is None:
            raise CurrencyApiError("Could not load exchange data. offline")
        return dict(self.currencies)

    def get_rates(self, base: str) -> CurrencyRates:
        if self.rates is None:
            raise CurrencyApiError("Could not load exchange data. offline")
        return CurrencyRates("2026-11-10", dict(self.rates))


SERVED_LIST = {"usd": "US Dollar", "eur": "Euro", "jpy": "Japanese Yen"}
SERVED_RATES = {"usd": Decimal("1"), "eur": Decimal("0.9"), "jpy": Decimal("150")}
KEPT_RATES = SavedCurrencyRates(
    "usd", "2026-11-10", (("usd", "1"), ("eur", "0.9"), ("jpy", "150"))
)


def open_currency_page(api: Any) -> Any:
    """The app with the currency page on screen and ``api`` behind it."""

    app = build_app()
    app.open_currency_conversion()
    assert app.currency_view is not None
    app.currency_view.api = api  # type: ignore[assignment]
    return app, app.currency_view


# --- what a save hands the page ------------------------------------------------


def test_the_page_is_handed_the_exchange_data_the_save_kept() -> None:
    app = build_app()
    app.data_store = StubStore(  # type: ignore[assignment]
        AppState(
            "Dark",
            (),
            currency_pair=("jpy", "eur"),
            currency_list=(("usd", "US Dollar"), ("eur", "Euro")),
            currency_rates=KEPT_RATES,
        )
    )

    asyncio.run(app.load_saved_data())
    app.open_currency_conversion()

    assert app.currency_view is not None
    assert app.currency_view.saved_currencies == {"usd": "US Dollar", "eur": "Euro"}
    assert app.currency_view.saved_rates == KEPT_RATES


def test_resetting_the_app_data_forgets_the_exchange_data() -> None:
    app = build_app()
    app.currency_list = dict(SERVED_LIST)
    app.currency_rates = KEPT_RATES

    app.reset_app_data()

    assert app.currency_list is None
    assert app.currency_rates is None
    assert app._state_snapshot().currency_list == ()
    assert app._state_snapshot().currency_rates is None


# --- what the app keeps after a live run ---------------------------------------


def test_a_live_run_is_kept_for_the_next_one() -> None:
    app, view = open_currency_page(StubApi(SERVED_LIST, SERVED_RATES))
    view.input_field.value = "100"

    asyncio.run(view.load_currencies())

    assert view.result_field.value == "90"
    assert app.currency_list == SERVED_LIST
    assert app.currency_rates == KEPT_RATES
    snapshot = app._state_snapshot()
    assert snapshot.currency_rates == KEPT_RATES
    assert sorted(snapshot.currency_list) == [
        ("eur", "Euro"),
        ("jpy", "Japanese Yen"),
        ("usd", "US Dollar"),
    ]


def test_keeping_the_same_rates_again_saves_nothing_new() -> None:
    app, view = open_currency_page(StubApi(SERVED_LIST, SERVED_RATES))
    view.input_field.value = "100"
    asyncio.run(view.load_currencies())
    saves = app.page.tasks.count("save_data")  # type: ignore[attr-defined]

    asyncio.run(view.run_conversion())

    assert app.currency_list == SERVED_LIST
    assert app.page.tasks.count("save_data") == saves  # type: ignore[attr-defined]


def test_an_offline_run_replaces_nothing_and_saves_nothing() -> None:
    app = build_app()
    app.data_store = StubStore(  # type: ignore[assignment]
        AppState(
            "Dark",
            (),
            currency_list=(("usd", "US Dollar"), ("eur", "Euro")),
            currency_rates=KEPT_RATES,
        )
    )
    asyncio.run(app.load_saved_data())
    app.open_currency_conversion()
    assert app.currency_view is not None
    app.currency_view.api = StubApi()  # type: ignore[assignment]
    app.currency_view.input_field.value = "100"
    saves = app.page.tasks.count("save_data")  # type: ignore[attr-defined]

    asyncio.run(app.currency_view.load_currencies())

    assert app.currency_list == {"usd": "US Dollar", "eur": "Euro"}
    assert app.currency_rates == KEPT_RATES
    assert app.page.tasks.count("save_data") == saves  # type: ignore[attr-defined]
    # The page still answered, out of what the save kept.
    assert app.currency_view.result_field.value == "90"
