"""How a calculated answer is rounded and written out.

The engine hands back the exact answer as text - an integer, or every decimal the
calculation context holds with the trailing zeros trimmed. This module is what
turns that into the number the display shows once the user has asked for a
precision: a fixed number of decimal places, a number of significant figures, a
switch into scientific notation past some size, which way a half rounds, and how
a large answer is broken into groups of three.

Grouping is a display style, so it has to be readable again: :func:`strip_grouping`
takes the separators back out of text the app feeds to the engine - the answer that
becomes the next expression after ``=``, a history card tapped back into the display,
the number a memory key works on.

It is deliberately pure and free of Flet, like the engines: the settings dialog
writes the choices, ``ui.py`` asks for the text, and the tests can do the same
without an app.
"""

import re
from dataclasses import dataclass
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)

# The rounding the settings offer, in the order the dialog lists them, with the
# Decimal rounding constant each one stands for.
ROUNDING_MODES = {
    "half-up": ROUND_HALF_UP,
    "half-even": ROUND_HALF_EVEN,
    "truncate": ROUND_DOWN,
}
ROUNDING_LABELS = {
    "half-up": "Half up",
    "half-even": "Half even",
    "truncate": "Truncate",
}
DEFAULT_ROUNDING = "half-up"

# What each precision dropdown offers. None is the "Automatic" entry: the answer
# is left exactly as the engine computed it.
DECIMAL_PLACE_CHOICES = (None, *range(0, 13))
SIGNIFICANT_FIGURE_CHOICES = (None, *range(1, 13))
# The size at which an answer switches to scientific notation, written as the
# power of ten it starts at: 6 means 1E-6 and 1E+6 and anything beyond.
SCIENTIFIC_THRESHOLD_CHOICES = (None, 3, 6, 9, 12)

# How a large answer is written in groups of three. The id names the style, the
# label spells it out with a sample number, and the separator is what actually
# goes into the text - "none" writes no separator at all.
GROUPING_MODES = ("comma", "space", "underscore", "none")
GROUPING_LABELS = {
    "comma": "Comma (1,234,567)",
    "space": "Space (1 234 567)",
    "underscore": "Underscore (1_234_567)",
    "none": "None (1234567)",
}
GROUPING_SEPARATORS = {
    "comma": ",",
    "space": " ",
    "underscore": "_",
    "none": "",
}
DEFAULT_GROUPING = "comma"

# The same separators read the other way round: one only groups when it sits
# between two digits with a full group of three behind it, which is exactly what
# ``apply_grouping`` writes - and nothing else. A comma between two function
# arguments ("max(1,2)") is therefore never mistaken for part of a number.
_GROUPING_CHARACTERS = "".join(
    re.escape(separator)
    for separator in GROUPING_SEPARATORS.values()
    if separator
)
GROUPED_DIGITS = re.compile(
    rf"(?<=[0-9])[{_GROUPING_CHARACTERS}](?=[0-9]{{3}}(?![0-9]))"
)


@dataclass(frozen=True)
class Precision:
    """The precision the user asked for; every field left None means automatic."""

    decimals: int | None = None
    sig_figs: int | None = None
    sci_threshold: int | None = None
    rounding: str = DEFAULT_ROUNDING
    grouping: str = DEFAULT_GROUPING

    def as_payload(self) -> dict:
        """The plain dict this is saved as."""

        return {
            "decimals": self.decimals,
            "sig_figs": self.sig_figs,
            "sci_threshold": self.sci_threshold,
            "rounding": self.rounding,
            "grouping": self.grouping,
        }


def _clean_choice(value: object, choices: tuple[int | None, ...]) -> int | None:
    """One precision dropdown's value, or None when it is not a listed choice.

    Saved data is not trusted: a value from an older version, or a hand-edited
    one, falls back to the automatic entry rather than failing the load.
    """

    return value if isinstance(value, int) and value in choices else None


def precision_from_payload(payload: object) -> Precision:
    """Read the saved precision, defaulting anything missing or unusable."""

    if not isinstance(payload, dict):
        return Precision()
    rounding = payload.get("rounding")
    grouping = payload.get("grouping")
    return Precision(
        decimals=_clean_choice(payload.get("decimals"), DECIMAL_PLACE_CHOICES),
        sig_figs=_clean_choice(
            payload.get("sig_figs"), SIGNIFICANT_FIGURE_CHOICES
        ),
        sci_threshold=_clean_choice(
            payload.get("sci_threshold"), SCIENTIFIC_THRESHOLD_CHOICES
        ),
        rounding=(
            rounding
            if isinstance(rounding, str) and rounding in ROUNDING_MODES
            else DEFAULT_ROUNDING
        ),
        grouping=(
            grouping
            if isinstance(grouping, str) and grouping in GROUPING_MODES
            else DEFAULT_GROUPING
        ),
    )


def _rounding_constant(precision: Precision) -> str:
    return ROUNDING_MODES.get(precision.rounding, ROUNDING_MODES[DEFAULT_ROUNDING])


def round_answer(value: Decimal, precision: Precision) -> Decimal:
    """Cut an answer to the requested precision.

    Decimal places win over significant figures when both are asked for - a fixed
    number of places is the plainer promise of the two - and neither is applied
    when both are automatic.
    """

    if not value.is_finite():
        return value

    if precision.decimals is not None:
        quantum = Decimal(1).scaleb(-precision.decimals)
    elif precision.sig_figs is not None:
        if value == 0:
            return Decimal(0)
        quantum = Decimal(1).scaleb(value.adjusted() - precision.sig_figs + 1)
    else:
        return value

    try:
        return value.quantize(quantum, rounding=_rounding_constant(precision))
    except (InvalidOperation, ValueError):
        # A number too big for the arithmetic context to hold at that quantum is
        # better shown unrounded than not shown at all.
        return value


def apply_grouping(text: str, grouping: str) -> str:
    """Write a fixed-notation number with the chosen thousands separator.

    Only the integer part is grouped, and from the right, which is where every
    style puts its separator. A sign and any decimal part stay where they are,
    and an answer of four digits or fewer is left alone - there is no group of
    three to separate yet.
    """

    separator = GROUPING_SEPARATORS.get(grouping, "")
    if not separator:
        return text

    sign = "-" if text.startswith("-") else ""
    if sign:
        text = text[1:]
    whole, point, fraction = text.partition(".")
    if len(whole) > 3:
        head = len(whole) % 3 or 3
        whole = separator.join(
            [whole[:head]] + [whole[i:i + 3] for i in range(head, len(whole), 3)]
        )
    return f"{sign}{whole}{point}{fraction}"


def strip_grouping(text: str) -> str:
    """Take the thousands separators back out of a number's text.

    The display writes what the app later reads back: after ``=`` the answer -
    grouped once a separator style is on - becomes the expression the next key
    continues, and history cards and the memory line hold the same text. Only a
    separator with a full group of three behind it is a grouping one, which is
    exactly how :func:`apply_grouping` writes one, so a comma sitting between two
    function arguments survives.
    """

    return GROUPED_DIGITS.sub("", text)


def format_answer(answer: str, precision: Precision) -> str:
    """The text the display shows for one calculated answer.

    Anything that is not a number - every error message the engine can raise -
    comes back untouched, so this never hides what went wrong.
    """

    try:
        value = Decimal(answer)
    except (InvalidOperation, ValueError):
        return answer
    if not value.is_finite():
        return answer

    value = round_answer(value, precision)
    if value == 0:
        # Both "-0" and "0.00" with nothing left in them read as plain zero.
        return "0"

    threshold = precision.sci_threshold
    if threshold is not None:
        adjusted = value.adjusted()
        if adjusted >= threshold or adjusted <= -threshold:
            # An exponent has no integer part to group, so a scientific-notation
            # answer keeps its digits to themselves.
            return format(value.normalize(), "E")

    if precision.decimals is not None:
        # A fixed number of decimal places keeps them, trailing zeros and all.
        return apply_grouping(format(value, "f"), precision.grouping)
    if value == value.to_integral_value():
        return apply_grouping(format(value, "f"), precision.grouping)
    return apply_grouping(format(value.normalize(), "f"), precision.grouping)
