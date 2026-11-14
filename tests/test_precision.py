"""The precision box: how many digits the app computes with, and how it writes them.

``precision.py`` is pure, so most of this runs with no app at all
(``pytest -k precision``). The app half builds the real app over the shared page
stub in ``tests/stub_page.py`` and checks what the display ends up holding.

The digit count moves the Decimal context the whole process calculates in, so
every test here gets the context it found back afterwards: the suite shares one
interpreter, and a context left at 5000 digits would change what other test files
compute.
"""

import threading
from decimal import DefaultContext, getcontext

import pytest

from calculate import calculate, is_number
from precision import (
    DEFAULT_PRECISION_DIGITS,
    GROUPING_MODES,
    PRECISION_DIGIT_CHOICES,
    Precision,
    apply_grouping,
    engine_precision,
    format_answer,
    precision_from_payload,
    set_engine_precision,
    strip_grouping,
)
from stub_page import build_app


@pytest.fixture(autouse=True)
def restore_decimal_context():
    """Put both Decimal contexts back the way the test found them."""

    live = (getcontext().prec, getcontext().rounding)
    default = (DefaultContext.prec, DefaultContext.rounding)
    yield
    for context, (digits, mode) in (
        (getcontext(), live),
        (DefaultContext, default),
    ):
        context.prec = digits
        context.rounding = mode


def compute(app, keys: str) -> str:
    """Type an expression on the pad, press "=", and hand back the display."""

    for key in keys:
        app.handle_key(key)
    app.handle_key("=")
    return app.expression


# --- the digit count, with no app in sight ------------------------------------


def test_an_app_starts_at_twelve_significant_digits() -> None:
    assert DEFAULT_PRECISION_DIGITS == 12
    assert engine_precision() == 12
    assert calculate("2/3", True) == "0.666666666667"
    assert calculate("10/3", True) == "3.33333333333"


def test_the_box_offers_counts_from_one_to_five_thousand() -> None:
    assert PRECISION_DIGIT_CHOICES == (
        1, 2, 3, 5, 8, 12, 50, 100, 200, 300, 400, 500, 1000, 5000,
    )
    assert DEFAULT_PRECISION_DIGITS in PRECISION_DIGIT_CHOICES


def test_the_count_moves_the_context_the_engine_runs_at() -> None:
    set_engine_precision(3)
    assert engine_precision() == 3
    assert calculate("2/3", True) == "0.667"

    set_engine_precision(50)
    assert engine_precision() == 50
    assert calculate("2/3", True) == "0." + "6" * 49 + "7"


def test_the_rounding_mode_decides_a_tie_in_the_arithmetic_itself() -> None:
    """1.25 needs three digits, so at two the tie is the arithmetic's to break."""

    set_engine_precision(2, "half-up")
    assert calculate("1.25+0", True) == "1.3"
    set_engine_precision(2, "half-even")
    assert calculate("1.25+0", True) == "1.2"
    set_engine_precision(2, "truncate")
    assert calculate("1.25+0", True) == "1.2"


def test_a_thread_started_later_computes_at_the_same_precision() -> None:
    """A new thread copies DefaultContext, not the running thread's context - which
    is why the setter writes both. Flet does not keep every handler on one thread."""

    set_engine_precision(50)

    seen: list[int] = []

    def read() -> None:
        seen.append(getcontext().prec)

    thread = threading.Thread(target=read)
    thread.start()
    thread.join()

    assert seen == [50]


def test_a_count_no_dropdown_offers_lands_on_the_default() -> None:
    set_engine_precision(7)

    assert engine_precision() == DEFAULT_PRECISION_DIGITS


# --- what the saved payload holds ---------------------------------------------


def test_a_saved_precision_that_makes_no_sense_falls_back_to_the_defaults() -> None:
    recovered = precision_from_payload(
        {
            "digits": 99,
            "sci_threshold": 4,
            "rounding": "up",
            "grouping": "dots",
        }
    )

    assert recovered.digits == DEFAULT_PRECISION_DIGITS
    assert recovered.sci_threshold is None
    assert recovered.rounding == "half-up"
    assert recovered.grouping == "comma"

    assert precision_from_payload(None) == Precision()


def test_a_save_from_before_the_digits_box_keeps_a_count_still_on_offer() -> None:
    """The box it replaced had a "Significant figures" dropdown: a saved count that
    is still a choice here carries over instead of being thrown away, and the
    decimal-places count it also had goes, because nothing asks for it now."""

    assert precision_from_payload({"decimals": 4, "sig_figs": 8}).digits == 8
    assert precision_from_payload({"sig_figs": 7}).digits == DEFAULT_PRECISION_DIGITS
    assert precision_from_payload({"decimals": 4}).digits == DEFAULT_PRECISION_DIGITS


# --- how an answer is written, which rounds nothing ---------------------------


def test_the_writing_choices_leave_the_digits_alone() -> None:
    """An answer arrives with the digits the engine used; the separator and the
    scientific-notation threshold only ever rearrange that text."""

    set_engine_precision(50)
    answer = "0." + "6" * 49 + "7"

    assert format_answer(answer, Precision()) == answer
    assert format_answer(answer, Precision(grouping="space")) == answer


def test_the_scientific_threshold_switches_both_ways() -> None:
    precision = Precision(sci_threshold=6)

    assert format_answer("1234567", precision) == "1.234567E+6"
    assert format_answer("0.0000012", precision) == "1.2E-6"
    assert format_answer("1234", precision) == "1,234"
    assert format_answer("0.001", precision) == "0.001"


def test_an_answer_with_nothing_in_it_reads_as_plain_zero() -> None:
    assert format_answer("-0", Precision()) == "0"
    assert format_answer("0.000", Precision()) == "0"


def test_an_error_message_is_shown_exactly_as_the_engine_wrote_it() -> None:
    precision = Precision(digits=3, sci_threshold=3)

    assert format_answer("Can't divide by 0", precision) == "Can't divide by 0"
    assert format_answer("Number Overflow", precision) == "Number Overflow"


# --- the thousands separator --------------------------------------------------


def test_a_large_answer_is_written_in_groups_of_three() -> None:
    assert format_answer("1234", Precision()) == "1,234"
    assert format_answer("1234567", Precision()) == "1,234,567"
    assert format_answer("-123456", Precision()) == "-123,456"
    # Three digits is not yet a number that needs separating.
    assert format_answer("123", Precision()) == "123"
    # Only the integer part is grouped, never the decimal one.
    assert format_answer("1234.5678", Precision()) == "1,234.5678"
    assert format_answer("0.5", Precision()) == "0.5"


def test_every_separator_style_writes_the_same_number() -> None:
    for grouping, expected in (
        ("comma", "1,234,567"),
        ("space", "1 234 567"),
        ("underscore", "1_234_567"),
        ("none", "1234567"),
    ):
        assert format_answer("1234567", Precision(grouping=grouping)) == expected
        assert apply_grouping("1234567", grouping) == expected


def test_a_scientific_notation_answer_keeps_its_digits_to_themselves() -> None:
    precision = Precision(sci_threshold=6)

    # An exponent has no integer part to group.
    assert format_answer("1234567", precision) == "1.234567E+6"
    # Below the threshold the same answer is still written in groups.
    assert format_answer("123456", precision) == "123,456"


def test_a_grouped_number_reads_back_as_the_number_it_shows() -> None:
    for grouped in ("1,234,567", "1 234 567", "1_234_567"):
        assert strip_grouping(grouped) == "1234567"

    assert strip_grouping("-1,234") == "-1234"
    assert strip_grouping("1,234.5") == "1234.5"
    # A separator only counts when a full group of three follows it, so a comma
    # between two function arguments is left alone.
    assert strip_grouping("1,2") == "1,2"
    assert strip_grouping("max(1,2345)") == "max(1,2345)"
    assert strip_grouping("123") == "123"


def test_the_engine_reads_a_grouped_answer_back_as_a_number() -> None:
    # After "=" the answer on screen becomes the expression the next key continues,
    # and a history card tapped back in holds the same text.
    assert calculate("1,234+1", True) == "1235"
    assert calculate("1 234 * 2", True) == "2468"
    assert calculate("-1_234", True) == "-1234"
    assert is_number("1,234") is True


# --- what the app does with it -----------------------------------------------


def set_precision(
    app,
    digits=None,
    sci=None,
    rounding="half-up",
    grouping="comma",
):
    """Pick the precision box the way the settings dialog's dropdowns do."""

    app.build_settings_dialog()
    app.settings_precision_digits.value = str(
        DEFAULT_PRECISION_DIGITS if digits is None else digits
    )
    app.settings_precision_scientific.value = "auto" if sci is None else str(sci)
    app.settings_precision_rounding.value = rounding
    app.settings_precision_grouping.value = grouping
    app.update_precision(None)


def test_the_settings_dialog_offers_the_whole_precision_box() -> None:
    app = build_app()
    dialog = app.build_settings_dialog()

    assert dialog.key == "settings-dialog"
    digits_box = app.settings_precision_digits
    assert digits_box in app.settings_content.controls
    assert digits_box.label == "Precision (Significant Digits)"
    assert digits_box.value == str(DEFAULT_PRECISION_DIGITS)
    assert [option.key for option in digits_box.options] == [
        str(choice) for choice in PRECISION_DIGIT_CHOICES
    ]
    # A digit count is never automatic: the arithmetic always runs at some number
    # of significant digits, so there is nothing to leave to the app.
    assert "auto" not in [option.key for option in digits_box.options]

    assert app.settings_precision_scientific in app.settings_content.controls
    assert app.settings_precision_scientific.value == "auto"
    assert app.settings_precision_rounding.value == "half-up"
    assert app.settings_precision_grouping in app.settings_content.controls
    assert app.settings_precision_grouping.value == "comma"
    assert [
        option.key for option in app.settings_precision_grouping.options
    ] == list(GROUPING_MODES)


def test_the_answer_comes_back_at_the_chosen_digit_count() -> None:
    app = build_app()
    set_precision(app, digits=3)

    assert compute(app, "2/3") == "0.667"


def test_the_live_preview_is_written_the_same_way_as_the_answer() -> None:
    app = build_app()
    set_precision(app, digits=3)
    for key in "2/3":
        app.handle_key(key)

    assert app.preview_value.value == "0.667"


def test_the_history_keeps_the_answer_the_user_was_shown() -> None:
    app = build_app()
    set_precision(app, digits=3)
    compute(app, "10/3")

    assert app.history[-1] == ("10/3", "3.33")


def test_the_rounding_choice_decides_how_the_arithmetic_breaks_a_tie() -> None:
    app = build_app()
    set_precision(app, digits=2, rounding="half-up")
    assert compute(app, "1.25+0") == "1.3"
    set_precision(app, digits=2, rounding="half-even")
    assert compute(app, "1.25+0") == "1.2"
    set_precision(app, digits=2, rounding="truncate")
    assert compute(app, "1.25+0") == "1.2"


def test_a_bigger_threshold_writes_the_answer_in_scientific_notation() -> None:
    app = build_app()
    set_precision(app, sci=6)

    assert compute(app, "1000000*7") == "7E+6"


def test_picking_the_count_moves_the_context_the_app_calculates_in() -> None:
    app = build_app()
    set_precision(app, digits=50)

    assert engine_precision() == 50


def test_a_smaller_count_cuts_the_answer_already_on_screen() -> None:
    app = build_app()
    assert compute(app, "1/3") == "0.333333333333"

    set_precision(app, digits=3)

    # The answer on screen is written at the current precision, so cutting the
    # count cuts it too - and the digits it keeps are the ones the arithmetic had.
    assert app.expression == "0.333"
    assert app.result_mode is True
    assert compute(app, "1/7") == "0.143"


def test_a_bigger_count_cannot_give_back_digits_that_were_never_computed() -> None:
    """Raising the count reaches the next calculation, not the digits of an answer
    already shortened: nothing remembers what the shorter arithmetic threw away."""

    app = build_app()
    set_precision(app, digits=3)
    assert compute(app, "1/3") == "0.333"

    set_precision(app, digits=12)

    assert compute(app, "1/3") == "0.333333333333"


def test_the_chosen_precision_is_saved_with_the_rest() -> None:
    app = build_app()
    set_precision(app, digits=50, rounding="truncate")

    snapshot = app._state_snapshot()

    assert snapshot.precision.digits == 50
    assert snapshot.precision.rounding == "truncate"


# --- what the separator does in the app ---------------------------------------


def test_a_large_answer_shows_up_grouped_on_the_display() -> None:
    app = build_app()

    assert compute(app, "1234567+0") == "1,234,567"


def test_the_live_preview_and_the_history_hold_the_same_writing() -> None:
    app = build_app()
    for key in "1234567*2":
        app.handle_key(key)

    assert app.preview_value.value == "2,469,134"
    app.handle_key("=")
    assert app.history[-1] == ("1234567*2", "2,469,134")


def test_choosing_a_separator_re_groups_the_answer_already_on_screen() -> None:
    app = build_app()
    compute(app, "1234567+0")

    set_precision(app, grouping="space")

    assert app.expression == "1 234 567"
    assert app.display.value == "1 234 567"
    assert app.precision.grouping == "space"


def test_a_grouped_answer_carries_on_into_the_next_calculation() -> None:
    app = build_app()

    assert compute(app, "1234567+0") == "1,234,567"
    for key in "+1":
        app.handle_key(key)
    app.handle_key("=")

    assert app.expression == "1,234,568"


def test_the_sign_key_keeps_a_grouped_answer_grouped() -> None:
    app = build_app()

    assert compute(app, "1234567*1") == "1,234,567"
    app.handle_key("±")

    assert app.expression == "-1,234,567"
    app.handle_key("=")
    assert app.expression == "-1,234,567"


def test_the_chosen_separator_is_saved_with_the_rest() -> None:
    app = build_app()
    set_precision(app, grouping="underscore")

    assert app._state_snapshot().precision.grouping == "underscore"

