import json

import pytest

from config import (
    ANGLE_DEG,
    ANGLE_GRAD,
    DEFAULT_ANGLE_MODE,
    DEFAULT_HISTORY_LENGTH,
    MAX_HISTORY_ITEMS,
)
from currency_api import SavedCurrencyRates
from data_storage import (
    AppDataStore,
    AppState,
    decode_state,
    encode_currency,
    encode_state,
    encode_pi,
)
from precision import Precision


def test_app_state_round_trips_theme_history_and_pi() -> None:
    state = AppState(
        theme="Light",
        history=(("1+2", "3"), ("pi", "3.141592653589")),
        pi_text="3.141592653589",
        pi_digits=12,
        primary_color="#123456",
        secondary_color="#ABCDEF",
    )

    assert decode_state(encode_state(state), encode_pi(state)) == state


def test_metadata_saves_leave_the_saved_pi_untouched() -> None:
    initial = AppState(
        theme="Dark",
        history=(),
        pi_text="3.141592653589",
        pi_digits=12,
    )

    updated = AppState(theme="Light", history=(("1+1", "2"),))

    restored = decode_state(encode_state(updated), encode_pi(initial))
    assert restored.theme == "Light"
    assert restored.history == (("1+1", "2"),)
    assert restored.pi_text == initial.pi_text
    assert restored.pi_digits == initial.pi_digits
    assert restored.primary_color is None
    assert restored.secondary_color is None


def test_the_memory_key_setting_round_trips_with_the_rest() -> None:
    state = AppState(theme="Dark", history=(), memory_keys_on_scientific=True)

    restored = decode_state(encode_state(state))

    assert restored.memory_keys_on_scientific is True


def test_a_save_from_before_the_memory_setting_leaves_the_keys_off() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    del payload["memory_keys_on_scientific"]

    restored = decode_state(json.dumps(payload))

    assert restored.memory_keys_on_scientific is False


def test_the_precision_round_trips_with_the_rest() -> None:
    state = AppState(
        theme="Dark",
        history=(),
        precision=Precision(digits=50, rounding="truncate"),
    )

    assert decode_state(encode_state(state)).precision == state.precision


def test_a_save_from_before_the_precision_box_starts_the_default_precision() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    del payload["precision"]

    assert decode_state(json.dumps(payload)).precision == Precision()


def test_the_separator_round_trips_with_the_precision() -> None:
    state = AppState(
        theme="Dark", history=(), precision=Precision(grouping="underscore")
    )

    assert decode_state(encode_state(state)).precision.grouping == "underscore"


def test_a_save_from_before_the_separator_leaves_it_on_commas() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    del payload["precision"]["grouping"]

    restored = decode_state(json.dumps(payload))

    assert restored.precision.grouping == "comma"
    assert restored.precision == Precision()


def test_the_history_length_round_trips_and_caps_at_the_ceiling() -> None:
    state = AppState(theme="Dark", history=(), history_limit=10)

    assert decode_state(encode_state(state)).history_limit == 10

    too_many = encode_state(AppState(theme="Dark", history=(), history_limit=5000))

    assert decode_state(too_many).history_limit == MAX_HISTORY_ITEMS


def test_a_save_from_before_the_history_setting_uses_the_default_length() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    del payload["history_limit"]

    restored = decode_state(json.dumps(payload))

    assert restored.history_limit == DEFAULT_HISTORY_LENGTH


def test_the_angle_mode_round_trips_with_the_rest() -> None:
    state = AppState(theme="Dark", history=(), angle_mode=ANGLE_GRAD)

    assert json.loads(encode_state(state))["angle_mode"] == "grad"
    assert decode_state(encode_state(state)).angle_mode == ANGLE_GRAD


def test_a_save_from_before_the_angle_mode_was_kept_starts_on_degrees() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    del payload["angle_mode"]

    restored = decode_state(json.dumps(payload))

    assert restored.angle_mode == DEFAULT_ANGLE_MODE == ANGLE_DEG


def test_a_saved_mode_the_app_does_not_offer_falls_back_to_degrees() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    payload["angle_mode"] = "turns"

    restored = decode_state(json.dumps(payload))

    assert restored.angle_mode == ANGLE_DEG


def test_a_loaded_history_is_cut_to_the_saved_length() -> None:
    history = [[f"{index}+1", str(index + 1)] for index in range(20)]
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": history,
            "primary_color": None,
            "secondary_color": None,
            "history_limit": 5,
        }
    )

    restored = decode_state(serialized)

    assert restored.history == tuple(
        (f"{index}+1", str(index + 1)) for index in range(15, 20)
    )


@pytest.mark.asyncio
async def test_client_storage_persists_metadata_and_pi_separately(monkeypatch) -> None:
    class MemoryPreferences:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def set(self, key: str, value: str) -> bool:
            self.values[key] = value
            return True

    preferences = MemoryPreferences()
    monkeypatch.setattr(
        "data_storage.ft.SharedPreferences",
        lambda: preferences,
    )
    store = AppDataStore()
    initial = AppState(
        "Dark",
        (),
        pi_text="3.141592653589",
        pi_digits=12,
    )
    await store.save(initial)
    await store.save(AppState("Light", (("1+1", "2"),)))

    assert await store.load() == AppState(
        "Light",
        (("1+1", "2"),),
        pi_text="3.141592653589",
        pi_digits=12,
    )


@pytest.mark.asyncio
async def test_clearing_the_store_forgets_everything_the_app_saved(monkeypatch) -> None:
    class MemoryPreferences:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def set(self, key: str, value: str) -> bool:
            self.values[key] = value
            return True

        async def remove(self, key: str) -> bool:
            return self.values.pop(key, None) is not None

    preferences = MemoryPreferences()
    monkeypatch.setattr("data_storage.ft.SharedPreferences", lambda: preferences)
    store = AppDataStore()
    await store.save(
        AppState(
            "Dark",
            (("1+1", "2"),),
            pi_text="3.141592653589",
            pi_digits=12,
            history_limit=10,
        )
    )
    assert await store.load() is not None

    await store.clear()

    assert await store.load() is None
    assert preferences.values == {}


def test_state_decoder_rejects_malformed_history() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [["1+1"]],
        }
    )

    with pytest.raises(ValueError, match="invalid entry"):
        decode_state(serialized)


def test_state_decoder_rejects_invalid_custom_colors() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [],
            "primary_color": "#12345",
        }
    )

    with pytest.raises(ValueError, match="six-digit hexadecimal"):
        decode_state(serialized)


def test_state_decoder_preserves_saved_custom_colors() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [],
            "primary_color": "#123456",
            "secondary_color": "#abcdef",
        }
    )

    state = decode_state(serialized)

    assert state.primary_color == "#123456"
    assert state.secondary_color == "#ABCDEF"


def test_state_decoder_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        decode_state("{")


def test_encoder_writes_json_arrays_for_history() -> None:
    state = AppState("Dark", (("1+1", "2"),))

    assert json.loads(encode_state(state))["history"] == [["1+1", "2"]]


# --- the remembered unit / currency pairs ------------------------------------


def test_the_unit_and_currency_pairs_round_trip_with_the_rest() -> None:
    state = AppState(
        "Dark",
        (),
        unit_pairs=(
            ("Volume Conversion", "volume_cubic_centimeter", "volume_cubic_meter"),
            ("Speed Conversion", "speed_mile_per_hour", "speed_kilometer_per_hour"),
        ),
        currency_pair=("jpy", "chf"),
    )

    assert decode_state(encode_state(state)) == state


def test_a_save_from_before_the_pairs_opens_nothing_remembered() -> None:
    payload = json.loads(encode_state(AppState("Dark", ())))
    del payload["unit_pairs"]
    del payload["currency_pair"]

    restored = decode_state(json.dumps(payload))

    assert restored.unit_pairs == ()
    assert restored.currency_pair is None


def test_the_decoder_keeps_the_last_pair_saved_for_a_page() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [],
            "unit_pairs": [
                ["Volume Conversion", "volume_milliliter", "volume_liter"],
                ["Volume Conversion", "volume_liter", "volume_cubic_meter"],
            ],
        }
    )

    assert decode_state(serialized).unit_pairs == (
        ("Volume Conversion", "volume_liter", "volume_cubic_meter"),
    )


def test_state_decoder_rejects_a_malformed_unit_pair() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [],
            "unit_pairs": [["Volume Conversion", "volume_liter"]],
        }
    )

    with pytest.raises(ValueError, match="unit pair contains an invalid entry"):
        decode_state(serialized)


def test_state_decoder_rejects_a_malformed_currency_pair() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [],
            "currency_pair": ["usd"],
        }
    )

    with pytest.raises(ValueError, match="currency pair is invalid"):
        decode_state(serialized)


def test_encoder_writes_json_arrays_for_the_pairs() -> None:
    state = AppState(
        "Dark",
        (),
        unit_pairs=(("Volume Conversion", "volume_liter", "volume_milliliter"),),
        currency_pair=("usd", "eur"),
    )
    payload = json.loads(encode_state(state))

    assert payload["unit_pairs"] == [
        ["Volume Conversion", "volume_liter", "volume_milliliter"]
    ]
    assert payload["currency_pair"] == ["usd", "eur"]


# --- the named variables ------------------------------------------------------


def test_the_named_variables_round_trip_with_the_rest() -> None:
    state = AppState(
        "Dark", (), variables=(("x", "4"), ("F", "12"), ("μ", "0.3"))
    )

    assert decode_state(encode_state(state)) == state


def test_a_save_from_before_the_variables_were_kept_carries_none() -> None:
    payload = json.loads(encode_state(AppState("Dark", ())))
    del payload["variables"]

    restored = decode_state(json.dumps(payload))

    assert restored.variables == ()


def test_the_decoder_keeps_the_last_value_saved_for_a_name() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "theme": "Dark",
            "history": [],
            "variables": [["x", "3"], ["x", "4"]],
        }
    )

    assert decode_state(serialized).variables == (("x", "4"),)


def test_state_decoder_rejects_a_malformed_variable() -> None:
    serialized = json.dumps(
        {"version": 1, "theme": "Dark", "history": [], "variables": [["x"]]}
    )

    with pytest.raises(ValueError, match="variables contain an invalid entry"):
        decode_state(serialized)


def test_state_decoder_rejects_a_variable_that_is_not_a_pair() -> None:
    serialized = json.dumps(
        {"version": 1, "theme": "Dark", "history": [], "variables": ["x=4"]}
    )

    with pytest.raises(ValueError, match="variables contain an invalid entry"):
        decode_state(serialized)


def test_encoder_writes_json_arrays_for_the_variables() -> None:
    state = AppState("Dark", (), variables=(("x", "4"),))

    assert json.loads(encode_state(state))["variables"] == [["x", "4"]]


def test_the_variables_are_saved_without_touching_the_saved_pi() -> None:
    initial = AppState("Dark", (), pi_text="3.141592653589", pi_digits=12)
    updated = AppState("Dark", (), variables=(("x", "4"),))

    restored = decode_state(encode_state(updated), encode_pi(initial))

    assert restored.variables == (("x", "4"),)
    assert restored.pi_text == initial.pi_text

# --- the exchange data the currency page falls back on ------------------------


def kept_state() -> AppState:
    """An app state carrying the currency list and table one good run served."""

    return AppState(
        "Dark",
        (),
        currency_list=(("usd", "US Dollar"), ("eur", "Euro")),
        currency_rates=SavedCurrencyRates(
            "usd", "2026-11-10", (("usd", "1"), ("eur", "0.9"))
        ),
    )


def test_the_exchange_data_round_trips_with_the_rest() -> None:
    state = kept_state()

    restored = decode_state(encode_state(state), None, encode_currency(state))

    assert restored == state


def test_a_save_from_before_the_exchange_data_was_kept_carries_none() -> None:
    restored = decode_state(encode_state(AppState("Dark", ())))

    assert restored.currency_list == ()
    assert restored.currency_rates is None


def test_a_metadata_save_leaves_the_kept_exchange_data_alone() -> None:
    initial = kept_state()
    updated = AppState("Light", (("1+1", "2"),))

    restored = decode_state(encode_state(updated), None, encode_currency(initial))

    assert restored.theme == "Light"
    assert restored.currency_list == initial.currency_list
    assert restored.currency_rates == initial.currency_rates


def test_the_state_save_carries_no_exchange_data() -> None:
    payload = json.loads(encode_state(kept_state()))

    assert "currency_list" not in payload
    assert "currency_rates" not in payload


def test_the_exchange_encoder_writes_json_arrays_under_its_own_keys() -> None:
    payload = json.loads(encode_currency(kept_state()))

    assert payload["version"] == 1
    assert payload["currencies"] == [["usd", "US Dollar"], ["eur", "Euro"]]
    assert payload["rates"] == {
        "base": "usd",
        "date": "2026-11-10",
        "table": [["usd", "1"], ["eur", "0.9"]],
    }


def test_kept_exchange_data_without_a_rate_table_keeps_its_list() -> None:
    serialized = json.dumps(
        {"version": 1, "currencies": [["usd", "US Dollar"]], "rates": None}
    )

    restored = decode_state(encode_state(AppState("Dark", ())), None, serialized)

    assert restored.currency_list == (("usd", "US Dollar"),)
    assert restored.currency_rates is None


def test_the_decoder_keeps_the_last_name_saved_for_a_currency() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "currencies": [["usd", "Dollar"], ["usd", "US Dollar"]],
            "rates": {
                "base": "usd",
                "date": "2026-11-10",
                "table": [["eur", "0.8"], ["eur", "0.9"]],
            },
        }
    )

    restored = decode_state(encode_state(AppState("Dark", ())), None, serialized)

    assert restored.currency_list == (("usd", "US Dollar"),)
    assert restored.currency_rates is not None
    assert restored.currency_rates.rates == (("eur", "0.9"),)


def test_state_decoder_rejects_currency_data_of_another_version() -> None:
    serialized = json.dumps({"version": 2, "currencies": []})

    with pytest.raises(ValueError, match="currency data has an unsupported format"):
        decode_state(encode_state(AppState("Dark", ())), None, serialized)


def test_state_decoder_rejects_a_malformed_currency_entry() -> None:
    serialized = json.dumps({"version": 1, "currencies": [["usd"]]})

    with pytest.raises(
        ValueError, match="currency list contains an invalid entry"
    ):
        decode_state(encode_state(AppState("Dark", ())), None, serialized)


def test_state_decoder_rejects_a_malformed_rate_row() -> None:
    serialized = json.dumps(
        {
            "version": 1,
            "rates": {"base": "usd", "date": "2026-11-10", "table": [["eur"]]},
        }
    )

    with pytest.raises(
        ValueError, match="exchange rates contain an invalid entry"
    ):
        decode_state(encode_state(AppState("Dark", ())), None, serialized)


def test_state_decoder_rejects_kept_rates_without_a_base_or_date() -> None:
    for table in [
        {"base": "", "date": "2026-11-10", "table": []},
        {"base": "usd", "date": "", "table": []},
        {"date": "2026-11-10", "table": []},
    ]:
        serialized = json.dumps({"version": 1, "rates": table})
        with pytest.raises(ValueError, match="exchange rates are invalid"):
            decode_state(encode_state(AppState("Dark", ())), None, serialized)


def test_state_decoder_rejects_kept_rates_without_a_table() -> None:
    serialized = json.dumps(
        {"version": 1, "rates": {"base": "usd", "date": "2026-11-10"}}
    )

    with pytest.raises(
        ValueError, match="exchange rates have an invalid table"
    ):
        decode_state(encode_state(AppState("Dark", ())), None, serialized)


@pytest.mark.asyncio
async def test_client_storage_keeps_the_exchange_data_in_its_own_key(
    monkeypatch,
) -> None:
    class MemoryPreferences:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def set(self, key: str, value: str) -> bool:
            self.values[key] = value
            return True

        async def remove(self, key: str) -> bool:
            return self.values.pop(key, None) is not None

    preferences = MemoryPreferences()
    monkeypatch.setattr("data_storage.ft.SharedPreferences", lambda: preferences)
    store = AppDataStore()

    await store.save(kept_state())
    assert set(preferences.values) == {
        "anycalc.app-state",
        "anycalc.currency-cache",
    }
    # A later save with nothing new to learn leaves the kept data where it is.
    await store.save(AppState("Light", (("1+1", "2"),)))

    restored = await store.load()

    assert restored is not None
    assert restored.theme == "Light"
    assert restored.currency_list == (("usd", "US Dollar"), ("eur", "Euro"))
    assert restored.currency_rates == kept_state().currency_rates

    await store.clear()
    assert preferences.values == {}
    assert await store.load() is None

