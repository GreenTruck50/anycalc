"""Engine tests for the calculator's own arithmetic - no window, no app.

``tests/test_conversion_engine.py`` covers the conversion graph; this file covers
the expression engine the two calculators sit on, which is why ``-k engine`` runs
both. Three features get pinned here:

* the ``%`` key, which on the scientific pad is the modulo operator and on the
  regular pad is the percent key of a physical calculator,
* :func:`src.calculate.apply_percent_operators`, which rewrites that postfix percent
  into something parseable, and
* the ``±`` key, backed by :func:`src.calculate.toggle_sign`, which edits the number
  the display rests on instead of appending an operator.

All are plain functions in ``src/calculate.py``, so they need no app host and run
under bare ``pytest``.
"""

import pytest

from calculate import (
    apply_percent_operators,
    calculate,
    toggle_sign,
)
from config import (
    ERROR_INVALID_EXPRESSION,
    ERROR_INVALID_RESULT,
)


def regular(expression: str) -> str:
    """Evaluate the way the regular calculator does: no names, no functions."""

    return calculate(expression, scientific=False)


def scientific(expression: str) -> str:
    """Evaluate the way the scientific calculator does: modulo, functions, names."""

    return calculate(expression, scientific=True)


# --- "%" on the scientific pad: the programmer's modulo operator --------------

@pytest.mark.parametrize(
    ("expression", "answer"),
    [
        ("9%2", "1"),
        ("10%5", "0"),
        ("5%3", "2"),
        ("6%4", "2"),
        ("7%2.5", "2"),
        ("(9+1)%4", "2"),
    ],
)
def test_percent_is_modulo_on_the_scientific_pad(expression, answer):
    assert scientific(expression) == answer


@pytest.mark.parametrize(
    ("expression", "answer"),
    [
        # Decimal's remainder truncates the quotient, so the result carries the
        # sign of the dividend - unlike Python's own -7 % 2, which is 1.
        ("-7%2", "-1"),
        ("7%-2", "1"),
    ],
)
def test_modulo_keeps_the_sign_of_the_dividend(expression, answer):
    assert scientific(expression) == answer


def test_modulo_by_zero_reports_an_error():
    with pytest.raises(ValueError) as error:
        scientific("5%0")
    assert str(error.value) == ERROR_INVALID_RESULT


# --- "%" on the regular pad: the percent key of a desk calculator -------------

PERCENT_CASES = [
    # on its own the key is simply "divide by a hundred"
    ("50%", "0.5"),
    ("10%", "0.1"),
    ("175%", "1.75"),
    ("200%", "2"),
    ("-5%", "-0.05"),
    # beside + or - it takes that share of the number on its left
    ("200+10%", "220"),
    ("200-10%", "180"),
    ("60+50%", "90"),
    ("200+-10%", "180"),
    ("200-+10%", "180"),
    # beside * or / it is the plain fraction
    ("200*10%", "20"),
    ("200/10%", "2000"),
    ("20%*30%", "0.06"),
    # the share is taken again off the running total, as on a real keypad
    ("200+10%+5%", "231"),
    ("200-10%-5%", "171"),
    ("50%+10%", "0.55"),
    # brackets and exponents belong to the number the key closes
    ("(200+100)%", "3"),
    ("1e2%", "1"),
    ("50%+10%*2", "0.7"),
]


@pytest.mark.parametrize(("expression", "answer"), PERCENT_CASES)
def test_percent_key_behaves_like_a_physical_calculator(expression, answer):
    assert regular(expression) == answer


@pytest.mark.parametrize(
    ("expression", "rewritten"),
    [
        ("50%", "_percent(50)"),
        ("200+10%", "200+_percent(10)"),
        ("200*10%", "200*_percent(10)"),
        ("(200+100)%", "_percent((200+100))"),
        ("sqrt(4)%", "_percent(sqrt(4))"),
        ("pi%", "_percent(pi)"),
        ("1e-5%", "_percent(1e-5)"),
        # nothing to take a percent of, so the key is ignored
        ("%", ""),
        ("200+%", "200+"),
        ("%50", "50"),
    ],
)
def test_percent_key_is_rewritten_before_parsing(expression, rewritten):
    assert apply_percent_operators(expression) == rewritten


def test_a_lone_percent_is_worth_nothing():
    """Pressing the key on an empty display is a no-op, not an error."""

    assert regular("%") == "0"


def test_percent_does_not_make_modulo_valid_on_the_regular_pad():
    """"9%2" is what a desk calculator calls a syntax error, not 1."""

    for expression in ("9%2", "9%2+1", "200+10%%3"):
        with pytest.raises(ValueError) as error:
            regular(expression)
        assert str(error.value) == ERROR_INVALID_EXPRESSION


def test_the_percent_rewrite_only_happens_on_the_regular_pad():
    """The scientific pad keeps the programmer's modulo, marker-free."""

    assert scientific("9%2") == "1"
    assert scientific("200+10%3") == "201"
    with pytest.raises(ValueError) as error:
        regular("200+10%3")
    assert str(error.value) == ERROR_INVALID_EXPRESSION


# (expression, result of pressing ±). The display rests on the last number typed,
# so the sign change lands there rather than at the front of the expression.
SIGN_CASES = [
    ("", ""),
    ("pi", "pi"),
    ("sin(", "sin("),
    ("5", "-5"),
    ("-5", "5"),
    ("-0.5", "0.5"),
    ("5-3", "5--3"),
    ("5--3", "5-3"),
    ("5*3", "5*-3"),
    ("5*-3", "5*3"),
    ("5*--3", "5*---3"),
    ("sqrt(4)", "sqrt(-4)"),
    ("sqrt(-4)", "sqrt(4)"),
    ("(5+3)", "(5+-3)"),
    ("2^3", "2^-3"),
    ("9%2", "9%-2"),
    # the regular pad's "%" closes a number, so the sign lands on that number
    ("10%", "-10%"),
    ("200+10%", "200+-10%"),
    # a literal with an exponent is one number, so its exponent is never touched
    ("1e5", "-1e5"),
    ("-1e-5", "1e-5"),
    # the pad spells "−" as "-", so a trailing minus is a subtraction already
    # underway and the sign belongs to the number that comes next
    ("5-", "5--"),
    ("5--", "5-"),
    ("5+", "5+-"),
]


@pytest.mark.parametrize(("expression", "expected"), SIGN_CASES)
def test_sign_change_edits_the_number_on_the_display(expression, expected):
    assert toggle_sign(expression) == expected


# On the scientific pad "%" is the modulo operator, so an expression ending on it
# is half-entered and the sign belongs to the number that comes next.
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("9%", "9%-"),
        ("9%2", "9%-2"),
        ("200+10%", "200+10%-"),
    ],
)
def test_sign_change_reads_the_scientific_pads_percent_as_an_operator(
    expression, expected
):
    assert toggle_sign(expression, percent_is_modulo=True) == expected


@pytest.mark.parametrize(("expression", "_expected"), SIGN_CASES)
def test_sign_change_is_its_own_inverse(expression, _expected):
    """A second press removes the sign rather than stacking another one."""

    assert toggle_sign(toggle_sign(expression)) == expression


@pytest.mark.parametrize(
    ("expression", "answer"),
    [
        ("5*3", "-15"),
        ("2^3", "0.125"),
        ("5-3", "8"),
        # "200+10%" is 220, and negating the 10 makes it 200 minus ten percent
        ("200+10%", "180"),
    ],
)
def test_a_sign_change_leaves_the_expression_evaluable(expression, answer):
    assert calculate(toggle_sign(expression), scientific=False) == answer


def test_a_negated_function_argument_reports_an_error():
    """sqrt(4) negated becomes sqrt(-4), which has no real answer."""

    with pytest.raises(ValueError):
        calculate(toggle_sign("sqrt(4)"), scientific=True)


def test_sign_change_flips_a_result_as_a_whole():
    """After "=" the display holds one number, and that number is what flips."""

    result = calculate("180", scientific=True)
    assert calculate(toggle_sign(result), scientific=True) == "-180"
