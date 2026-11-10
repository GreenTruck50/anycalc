import json

import pytest

from config import DEFAULT_HISTORY_LENGTH, MAX_HISTORY_ITEMS
from data_storage import (
    AppDataStore,
    AppState,
    decode_state,
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
        precision=Precision(decimals=3, sig_figs=None, rounding="truncate"),
    )

    assert decode_state(encode_state(state)).precision == state.precision


def test_a_save_from_before_the_precision_box_leaves_it_automatic() -> None:
    payload = json.loads(encode_state(AppState(theme="Dark", history=())))
    del payload["precision"]

    assert decode_state(json.dumps(payload)).precision == Precision()


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
