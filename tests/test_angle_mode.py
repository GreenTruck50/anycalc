"""The angle mode sin/cos/tan read their argument in.

Three modes - degrees, radians, gradians - reachable two ways: the header's button
cycles them, and Settings offers a dropdown. The mode is kept between runs, so it
rides along in the saved app state beside the theme and the history.

No app host is needed - ``pytest -k angle`` runs this file on its own. The engine
is called directly for what each mode means arithmetically; the app is built over
the shared page stub in ``tests/stub_page.py`` for the button, the dropdown and
the save. What storage tolerates in a saved mode is checked in
``tests/test_data_storage.py``.
"""

import asyncio
import types
from typing import cast

import pytest

from calculate import calculate
from config import (
    ANGLE_DEG,
    ANGLE_GRAD,
    ANGLE_MODE_LABELS,
    ANGLE_MODES,
    ANGLE_MODE_NAMES,
    ANGLE_RAD,
    DEFAULT_ANGLE_MODE,
)
from data_storage import AppState, decode_state, encode_state
from stub_page import build_app, fire
from ui import AnycalcApp


def trig_answer(expression: str, mode: str) -> float:
    """What the engine makes of a trig call in one named mode."""

    return float(calculate(expression, scientific=True, angle_mode=mode))


def press_angle_button(app: AnycalcApp) -> None:
    """Tap the header's angle button."""

    fire(app.angle_button.on_click, types.SimpleNamespace(control=app.angle_button))


def angle_label(app: AnycalcApp) -> str:
    """The word the header's button is showing."""

    return cast(str, app.angle_label.value)


def preview_of(app: AnycalcApp, expression: str) -> str:
    """The live answer the display shows under an expression."""

    app.expression = expression
    app.result_mode = False
    app.refresh_preview()
    return cast(str, app.preview_value.value)


def restore(app: AnycalcApp, state: AppState) -> None:
    """Hand a saved state to the app the way client storage would."""

    class StubStore:
        async def load(self) -> AppState:
            return state

        async def save(self, saved: AppState, include_pi: bool = False) -> None:
            del saved, include_pi

        async def clear(self) -> None:
            pass

    app.data_store = StubStore()  # type: ignore[assignment]
    asyncio.run(app.load_saved_data())


# --- what each mode means ------------------------------------------------------


def test_degrees_split_a_quarter_turn_into_90_parts() -> None:
    assert trig_answer("sin(30)", ANGLE_DEG) == pytest.approx(0.5)
    assert trig_answer("cos(60)", ANGLE_DEG) == pytest.approx(0.5)
    assert trig_answer("tan(45)", ANGLE_DEG) == pytest.approx(1.0)


def test_gradians_split_a_whole_turn_into_400_parts() -> None:
    # 100 gon is a quarter turn and 200 gon a half, so they answer what degrees
    # answers for 90 and 180.
    assert trig_answer("sin(100)", ANGLE_GRAD) == pytest.approx(1.0)
    assert trig_answer("cos(200)", ANGLE_GRAD) == pytest.approx(-1.0)
    assert trig_answer("sin(50)", ANGLE_GRAD) == pytest.approx(
        trig_answer("sin(45)", ANGLE_DEG)
    )


def test_radians_are_what_the_engine_reads_when_no_mode_is_named() -> None:
    # The conversion formulas and the Pi page call the engine without a mode, so
    # they keep the radians they have always had.
    assert trig_answer("sin(pi/2)", ANGLE_RAD) == pytest.approx(1.0)
    assert calculate("sin(30)", True) == calculate("sin(30)", True, ANGLE_RAD)


def test_the_three_modes_disagree_about_the_same_number() -> None:
    assert trig_answer("sin(30)", ANGLE_DEG) == pytest.approx(0.5)
    assert trig_answer("sin(30)", ANGLE_RAD) == pytest.approx(-0.9880316240928618)
    assert trig_answer("sin(30)", ANGLE_GRAD) == pytest.approx(0.45399049973954675)


# --- the header's button -------------------------------------------------------


def test_the_angle_button_starts_on_degrees() -> None:
    app = build_app()

    assert app.angle_mode == DEFAULT_ANGLE_MODE
    assert angle_label(app) == "DEG"


def test_the_angle_button_cycles_through_every_mode_and_rounds_again() -> None:
    app = build_app()

    for mode in (ANGLE_RAD, ANGLE_GRAD, ANGLE_DEG):
        press_angle_button(app)
        assert app.angle_mode == mode
        assert angle_label(app) == ANGLE_MODE_LABELS[mode]


def test_the_mode_the_button_reaches_is_the_mode_the_pad_uses() -> None:
    app = build_app()
    app.set_mode(1)
    press_angle_button(app)
    press_angle_button(app)

    # sin(100) is 0.98... in degrees; a whole 1 only in gradians.
    assert preview_of(app, "sin(100)") == "1"


def test_a_button_press_saves_the_mode_it_moved_to() -> None:
    app = build_app()
    press_angle_button(app)

    assert '"angle_mode":"rad"' in encode_state(app._state_snapshot())


# --- the Settings dropdown -----------------------------------------------------


def test_settings_offers_every_mode_by_its_full_name() -> None:
    app = build_app()
    app.build_settings_dialog()
    dropdown = app.settings_angle_mode

    assert dropdown.key == "settings-angle-mode"
    assert dropdown in app.settings_content.controls
    assert [option.key for option in dropdown.options] == list(ANGLE_MODES)
    assert [option.text for option in dropdown.options] == [
        ANGLE_MODE_NAMES[mode] for mode in ANGLE_MODES
    ]
    assert dropdown.value == DEFAULT_ANGLE_MODE


def test_picking_a_mode_in_settings_moves_the_button_and_the_pad() -> None:
    app = build_app()
    app.set_mode(1)
    app.build_settings_dialog()
    app.settings_angle_mode.value = ANGLE_GRAD
    fire(app.settings_angle_mode.on_select, types.SimpleNamespace())

    assert app.angle_mode == ANGLE_GRAD
    assert angle_label(app) == "GRAD"
    assert preview_of(app, "sin(100)") == "1"
    assert '"angle_mode":"grad"' in encode_state(app._state_snapshot())


def test_the_open_settings_dialog_follows_a_mode_reached_from_the_button() -> None:
    app = build_app()
    app.build_settings_dialog()
    press_angle_button(app)
    press_angle_button(app)

    app.sync_settings_controls()

    assert app.settings_angle_mode.value == ANGLE_GRAD


def test_resetting_the_app_data_puts_the_mode_back_to_degrees() -> None:
    app = build_app()
    app.build_settings_dialog()
    app.settings_angle_mode.value = ANGLE_GRAD
    fire(app.settings_angle_mode.on_select, types.SimpleNamespace())

    app.reset_app_data()

    assert app.angle_mode == ANGLE_DEG
    assert angle_label(app) == "DEG"
    assert app.settings_angle_mode.value == ANGLE_DEG


# --- the save ------------------------------------------------------------------


def test_a_saved_mode_comes_back_onto_the_button() -> None:
    app = build_app()
    restore(app, AppState(theme="Dark", history=(), angle_mode=ANGLE_GRAD))

    assert app.angle_mode == ANGLE_GRAD
    assert angle_label(app) == "GRAD"


def test_a_save_written_before_the_mode_was_kept_starts_on_degrees() -> None:
    app = build_app()
    app.build_settings_dialog()
    app.settings_angle_mode.value = ANGLE_GRAD
    fire(app.settings_angle_mode.on_select, types.SimpleNamespace())

    restore(app, AppState(theme="Dark", history=()))

    assert app.angle_mode == ANGLE_DEG
    assert angle_label(app) == "DEG"


def test_the_angle_mode_round_trips_through_client_storage() -> None:
    state = AppState(theme="Dark", history=(), angle_mode=ANGLE_GRAD)

    assert decode_state(encode_state(state)) == state

