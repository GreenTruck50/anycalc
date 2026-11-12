"""Persistence for the app's theme, selected colors, calculation history, pi, and
the unit and currency pairs its pages last opened on."""

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

import flet as ft

from config import DEFAULT_HISTORY_LENGTH, MAX_HISTORY_ITEMS
from precision import Precision, precision_from_payload
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
    precision: Precision = Precision()
    history_limit: int = DEFAULT_HISTORY_LENGTH
    # (conversion name, from unit id, to unit id) - one entry per conversion page
    # the user has chosen units on. A tuple rather than a dict so the state stays
    # hashable and JSON round-trips the way the history does.
    unit_pairs: tuple[tuple[str, str, str], ...] = ()
    currency_pair: Optional[tuple[str, str]] = None


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

    history_limit = payload.get("history_limit")
    if (
        not isinstance(history_limit, int)
        or isinstance(history_limit, bool)
        or history_limit < 1
    ):
        history_limit = DEFAULT_HISTORY_LENGTH
    history_limit = min(history_limit, MAX_HISTORY_ITEMS)

    # The pairs are keyed by conversion name, so a save that names the same page
    # twice keeps the last entry for it rather than the first.
    remembered: dict[str, tuple[str, str]] = {}
    saved_pairs = payload.get("unit_pairs")
    if saved_pairs is None:
        # A save from before the pages remembered their units.
        saved_pairs = []
    if not isinstance(saved_pairs, list):
        raise ValueError("saved unit pairs are missing or invalid")
    for entry in saved_pairs:
        if (
            not isinstance(entry, list)
            or len(entry) != 3
            or not all(isinstance(value, str) and value for value in entry)
        ):
            raise ValueError("saved unit pair contains an invalid entry")
        remembered[entry[0]] = (entry[1], entry[2])

    currency_pair = payload.get("currency_pair")
    if currency_pair is not None:
        if (
            not isinstance(currency_pair, list)
            or len(currency_pair) != 2
            or not all(isinstance(code, str) and code for code in currency_pair)
        ):
            raise ValueError("saved currency pair is invalid")
        currency_pair = (currency_pair[0], currency_pair[1])

    return AppState(
        theme=theme,
        history=tuple(checked_history[-history_limit:]),
        pi_text=pi_text,
        pi_digits=pi_digits,
        primary_color=primary_color,
        secondary_color=secondary_color,
        memory_keys_on_scientific=memory_keys,
        precision=precision_from_payload(payload.get("precision")),
        history_limit=history_limit,
        unit_pairs=tuple(
            (name, source, target)
            for name, (source, target) in remembered.items()
        ),
        currency_pair=currency_pair,
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
            "precision": state.precision.as_payload(),
            "history_limit": state.history_limit,
            "unit_pairs": [list(entry) for entry in state.unit_pairs],
            "currency_pair": (
                list(state.currency_pair) if state.currency_pair is not None else None
            ),
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

    async def clear(self) -> None:
        """Drop every key the app has stored, settings, history and pi alike.

        "Reset all app data" is the only caller. The keys are removed rather than
        overwritten so a reset really is what the user was promised: the next
        start finds nothing at all.
        """

        async with self._save_lock:
            for key in (_STATE_STORAGE_KEY, _PI_STORAGE_KEY):
                await self.preferences.remove(key)

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
