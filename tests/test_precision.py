"""The precision box: how an answer is rounded and written out.

``precision.py`` is pure, so most of this runs with no app at all
(``pytest -k precision``). The app half builds the real app over the shared page
stub in ``tests/stub_page.py`` and checks what the display ends up holding.
"""

from decimal import Decimal

from calculate import calculate, is_number
from precision import (
    GROUPING_MODES,
    Precision,
    apply_grouping,
    format_answer,
    precision_from_payload,
    round_answer,
    strip_grouping,
)
from stub_page import build_app


def compute(app, keys: str) -> str:
    """Type an expression on the pad, press "=", and hand back the display."""

    for key in keys:
        app.handle_key(key)
    app.handle_key("=")
    return app.expression


# --- rounding, with no app in sight ------------------------------------------


def test_the_default_precision_leaves_the_engines_answer_alone() -> None:
    answer = "0.66666666666666666666666666666666666666666666666666"

    assert format_answer(answer, Precision()) == answer


def test_decimal_places_cut_the_answer_and_keep_the_places() -> None:
    assert format_answer("0.6666666666", Precision(decimals=4)) == "0.6667"
    assert format_answer("3.5", Precision(decimals=2)) == "3.50"
    assert format_answer("2", Precision(decimals=2)) == "2.00"


def test_significant_figures_count_from_the_first_nonzero_digit() -> None:
    assert format_answer("123456", Precision(sig_figs=3)) == "123,000"
    assert format_answer("0.00123456", Precision(sig_figs=3)) == "0.00123"


def test_half_up_half_even_and_truncate_round_the_same_half_apart() -> None:
    assert round_answer(Decimal("2.5"), Precision(decimals=0)) == Decimal("3")
    assert round_answer(
        Decimal("2.5"), Precision(decimals=0, rounding="half-even")
    ) == Decimal("2")
    assert round_answer(
        Decimal("2.5"), Precision(decimals=0, rounding="truncate")
    ) == Decimal("2")
    assert round_answer(
        Decimal("-2.5"), Precision(decimals=0, rounding="half-even")
    ) == Decimal("-2")
    assert round_answer(
        Decimal("-0.9"), Precision(decimals=0, rounding="truncate")
    ) == Decimal("0")


def test_decimal_places_win_when_both_counts_are_asked_for() -> None:
    assert format_answer("0.12345", Precision(decimals=3, sig_figs=2)) == "0.123"


def test_the_scientific_threshold_switches_both_ways() -> None:
    precision = Precision(sci_threshold=6)

    assert format_answer("1234567", precision) == "1.234567E+6"
    assert format_answer("0.0000012", precision) == "1.2E-6"
    assert format_answer("1234", precision) == "1,234"
    assert format_answer("0.001", precision) == "0.001"


def test_an_answer_with_no_digits_left_reads_as_plain_zero() -> None:
    assert format_answer("-0.0004", Precision(decimals=2)) == "0"


def test_an_error_message_is_shown_exactly_as_the_engine_wrote_it() -> None:
    precision = Precision(decimals=2, sig_figs=1, sci_threshold=3)

    assert format_answer("Can't divide by 0", precision) == "Can't divide by 0"
    assert format_answer("Number Overflow", precision) == "Number Overflow"


def test_a_saved_precision_that_makes_no_sense_falls_back_to_automatic() -> None:
    recovered = precision_from_payload(
        {
            "decimals": 99,
            "sig_figs": "three",
            "sci_threshold": 4,
            "rounding": "up",
            "grouping": "dots",
        }
    )

    assert recovered.decimals is None
    assert recovered.sig_figs is None
    assert recovered.sci_threshold is None
    assert recovered.rounding == "half-up"
    assert recovered.grouping == "comma"

    assert precision_from_payload(None) == Precision()


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
    assert calculate("1,234+1", scientific=True) == "1235"
    assert calculate("1 234 * 2", scientific=True) == "2468"
    assert calculate("-1_234", scientific=True) == "-1234"
    assert is_number("1,234") is True


# --- what the app does with it -----------------------------------------------


def set_precision(
    app,
    decimals=None,
    sig_figs=None,
    sci=None,
    rounding="half-up",
    grouping="comma",
):
    """Pick the precision box the way the settings dialog's dropdowns do."""

    app.build_settings_dialog()
    app.settings_precision_decimals.value = (
        "auto" if decimals is None else str(decimals)
    )
    app.settings_precision_sig_figs.value = (
        "auto" if sig_figs is None else str(sig_figs)
    )
    app.settings_precision_scientific.value = "auto" if sci is None else str(sci)
    app.settings_precision_rounding.value = rounding
    app.settings_precision_grouping.value = grouping
    app.update_precision(None)


def test_the_settings_dialog_offers_the_whole_precision_box() -> None:
    app = build_app()
    dialog = app.build_settings_dialog()

    assert dialog.key == "settings-dialog"
    for control in (
        app.settings_precision_decimals,
        app.settings_precision_sig_figs,
        app.settings_precision_scientific,
    ):
        assert control in app.settings_content.controls
        assert control.value == "auto"
    assert app.settings_precision_rounding.value == "half-up"
    assert app.settings_precision_grouping in app.settings_content.controls
    assert app.settings_precision_grouping.value == "comma"
    assert [
        option.key for option in app.settings_precision_grouping.options
    ] == list(GROUPING_MODES)


def test_the_answer_is_written_with_the_chosen_decimal_places() -> None:
    app = build_app()
    set_precision(app, decimals=4)

    assert compute(app, "2/3") == "0.6667"


def test_the_live_preview_is_written_the_same_way_as_the_answer() -> None:
    app = build_app()
    set_precision(app, decimals=3)
    for key in "2/3":
        app.handle_key(key)

    assert app.preview_value.value == "0.667"


def test_the_history_keeps_the_answer_the_user_was_shown() -> None:
    app = build_app()
    set_precision(app, decimals=2)
    compute(app, "10/3")

    assert app.history[-1] == ("10/3", "3.33")


def test_rounding_even_shows_up_in_the_answer() -> None:
    app = build_app()
    set_precision(app, decimals=0, rounding="half-even")

    assert compute(app, "2.5") == "2"


def test_a_bigger_threshold_writes_the_answer_in_scientific_notation() -> None:
    app = build_app()
    set_precision(app, sci=6)

    assert compute(app, "1000000*7") == "7E+6"


def test_choosing_a_precision_re_shows_the_answer_already_on_screen() -> None:
    app = build_app()
    compute(app, "1/3")

    set_precision(app, decimals=2)

    assert app.expression == "0.33"
    assert app.result_mode is True


def test_the_chosen_precision_is_saved_with_the_rest() -> None:
    app = build_app()
    set_precision(app, decimals=4, rounding="truncate")

    snapshot = app._state_snapshot()

    assert snapshot.precision.decimals == 4
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
