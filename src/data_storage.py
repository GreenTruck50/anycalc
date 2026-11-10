"""Persistence for the app's theme, selected colors, calculation history, and pi."""

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

import flet as ft

from config import MAX_HISTORY_ITEMS
import styles

_STATE_STORAGE_KEY = "anycalc.app-state"
_PI_STORAGE_KEY = "anycalc.program-pi"
_STATE_VERSION = 1


@dataclass(frozen=True)
class AppState:
    theme: str
    history: tuple[tuple[str, str], ...]
    pi_text: Optional[str] = None
    pi_digits: Optional[int] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    memory_keys_on_scientific: bool = False


def _decode_json(serialized: str) -> object:
    try:
        return json.loads(serialized)
    except json.JSONDecodeError as error:
        raise ValueError(f"saved data is not valid JSON: {error}") from error


def decode_state(
    serialized: str,
    pi_serialized: Optional[str] = None,
) -> AppState:
    """Decode and validate persisted metadata and, when present, the active pi."""

    payload = _decode_json(serialized)
    if not isinstance(payload, dict) or payload.get("version") != _STATE_VERSION:
        raise ValueError("saved data has an unsupported format")

    theme = payload.get("theme")
    history = payload.get("history")
    if not isinstance(theme, str):
        raise ValueError("saved theme is missing or invalid")
    if not isinstance(history, list):
        raise ValueError("saved history is missing or invalid")
    primary_color = payload.get("primary_color")
    secondary_color = payload.get("secondary_color")
    if primary_color is not None:
        primary_color = styles.normalize_color(primary_color)
    if secondary_color is not None:
        secondary_color = styles.normalize_color(secondary_color)

    checked_history: list[tuple[str, str]] = []
    for entry in history:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not all(isinstance(value, str) for value in entry)
        ):
            raise ValueError("saved history contains an invalid entry")
        checked_history.append((entry[0], entry[1]))

    pi_text = None
    pi_digits = None
    if pi_serialized is not None:
        pi_payload = _decode_json(pi_serialized)
        if (
            not isinstance(pi_payload, dict)
            or pi_payload.get("version") != _STATE_VERSION
        ):
            raise ValueError("saved pi has an unsupported format")
        pi_text = pi_payload.get("value")
        pi_digits = pi_payload.get("digits")
        if not isinstance(pi_text, str):
            raise ValueError("saved pi value is invalid")
        if not isinstance(pi_digits, int) or isinstance(pi_digits, bool):
            raise ValueError("saved pi precision is invalid")

    memory_keys = payload.get("memory_keys_on_scientific")
    if not isinstance(memory_keys, bool):
        # A save from before the memory keys were a setting never asked for them.
        memory_keys = False

    return AppState(
        theme=theme,
        history=tuple(checked_history[-MAX_HISTORY_ITEMS:]),
        pi_text=pi_text,
        pi_digits=pi_digits,
        primary_color=primary_color,
        secondary_color=secondary_color,
        memory_keys_on_scientific=memory_keys,
    )


def encode_state(state: AppState) -> str:
    """Serialize theme, RGB color values, and history as compact JSON."""

    return json.dumps(
        {
            "version": _STATE_VERSION,
            "theme": state.theme,
            "history": state.history,
            "primary_color": state.primary_color,
            "secondary_color": state.secondary_color,
            "memory_keys_on_scientific": state.memory_keys_on_scientific,
        },
        separators=(",", ":"),
    )


def encode_pi(state: AppState) -> str:
    """Serialize the active pi separately from frequently updated app metadata."""

    if state.pi_text is None or state.pi_digits is None:
        raise ValueError("cannot save a pi without its value and precision")
    return json.dumps(
        {
            "version": _STATE_VERSION,
            "value": state.pi_text,
            "digits": state.pi_digits,
        },
        separators=(",", ":"),
    )


class AppDataStore:
    """Keep one Flet client-preferences service alive for the app session."""

    def __init__(self) -> None:
        self.preferences = ft.SharedPreferences()
        self._save_lock = asyncio.Lock()

    async def load(self) -> Optional[AppState]:
        serialized = await self.preferences.get(_STATE_STORAGE_KEY)
        if serialized is None:
            return None
        if not isinstance(serialized, str):
            raise ValueError("saved app data is not text")
        pi_serialized = await self.preferences.get(_PI_STORAGE_KEY)
        if pi_serialized is not None and not isinstance(pi_serialized, str):
            raise ValueError("saved pi data is not text")
        return decode_state(serialized, pi_serialized)

    async def save(self, state: AppState) -> None:
        async with self._save_lock:
            serialized = await asyncio.to_thread(encode_state, state)
            saved = await self.preferences.set(_STATE_STORAGE_KEY, serialized)
            if not saved:
                raise OSError("Flet client storage did not save application data")
            if state.pi_text is not None:
                pi_serialized = await asyncio.to_thread(encode_pi, state)
                saved_pi = await self.preferences.set(
                    _PI_STORAGE_KEY,
                    pi_serialized,
                )
                if not saved_pi:
                    raise OSError("Flet client storage did not save the active pi")
