"""How many digits the app computes with, and how an answer is written out.

Two things live here because they are the same decision seen from either side.

*The engine side.* :func:`set_engine_precision` moves the Decimal context the
whole process calculates in - how many significant digits a calculation works
with, and which way a tied digit rounds there. The Settings box "Precision
(Significant Digits)" is the only thing that asks for it, and the answer the
engine hands back already carries at most that many significant digits: every
Decimal operation rounds to the context, so nothing here has to cut an answer
down afterwards.

*The display side.* The engine hands back its answer as text - an integer, or
every decimal the context holds with the trailing zeros trimmed.
:func:`format_answer` turns that into what the display shows: a switch into
scientific notation past some size, and how a large answer is broken into groups
of three.

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
    DefaultContext,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    getcontext,
)

from config import DECIMAL_PRECISION

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

# What the "Precision (Significant Digits)" box offers. The count is how many
# significant digits a calculation works with, so the short end is a pocket
# calculator and the long end is what lets a hundred-thousand-digit pi actually be
# multiplied. There is no "Automatic" entry: the context always computes at some
# number of digits, and DEFAULT_PRECISION_DIGITS is where an app starts.
PRECISION_DIGIT_CHOICES = (
    1, 2, 3, 5, 8, 12, 50, 100, 200, 300, 400, 500, 1000, 5000,
)
DEFAULT_PRECISION_DIGITS = DECIMAL_PRECISION

# What the scientific-notation dropdown offers. None is the "Automatic" entry: the
# answer keeps the plain digits the engine writes.
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
    """What the user asked the app to compute with and how to write it out.

    ``digits`` is the Decimal context's precision - how many significant digits a
    calculation works with - and it is the one choice that is never automatic.
    ``sci_threshold`` left None means an answer keeps the plain digits the engine
    writes.
    """

    digits: int = DEFAULT_PRECISION_DIGITS
    sci_threshold: int | None = None
    rounding: str = DEFAULT_ROUNDING
    grouping: str = DEFAULT_GROUPING

    def as_payload(self) -> dict:
        """The plain dict this is saved as."""

        return {
            "digits": self.digits,
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


def _clean_digits(value: object, legacy: object) -> int:
    """The digits choice, or the default when the saved value is not one.

    A save written before this box existed carries ``sig_figs`` - the same kind of
    count, from a narrower list - so a value that is still a listed choice carries
    over instead of being thrown away. ``decimals``, which this box replaced, is
    simply gone.
    """

    for candidate in (value, legacy):
        if isinstance(candidate, int) and candidate in PRECISION_DIGIT_CHOICES:
            return candidate
    return DEFAULT_PRECISION_DIGITS


def precision_from_payload(payload: object) -> Precision:
    """Read the saved precision, defaulting anything missing or unusable."""

    if not isinstance(payload, dict):
        return Precision()
    rounding = payload.get("rounding")
    grouping = payload.get("grouping")
    return Precision(
        digits=_clean_digits(payload.get("digits"), payload.get("sig_figs")),
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


def _rounding_constant(mode: str) -> str:
    return ROUNDING_MODES.get(mode, ROUNDING_MODES[DEFAULT_ROUNDING])


def set_engine_precision(
    digits: int,
    rounding: str = DEFAULT_ROUNDING,
) -> None:
    """Move the Decimal context every calculation in the process runs in.

    A count no dropdown offers - an older save, a hand-edited one - lands on the
    default rather than leaving the context at a size the user cannot ask for. The
    rounding mode travels with it, so the tie-breaking the settings promise is the
    tie-breaking the arithmetic itself uses.

    Two contexts are written on purpose. A thread created later copies
    ``DefaultContext`` rather than the running thread's context, and Flet does not
    keep every event handler on one thread, so a change that reached only
    ``getcontext()`` would apply to some calculations and not to others.
    """

    if not isinstance(digits, int) or digits not in PRECISION_DIGIT_CHOICES:
        digits = DEFAULT_PRECISION_DIGITS
    mode = _rounding_constant(rounding)
    for context in (getcontext(), DefaultContext):
        context.prec = digits
        context.rounding = mode


def engine_precision() -> int:
    """How many significant digits calculations run at right now."""

    return getcontext().prec


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

    The answer arrives with the digits the engine computed - every operation
    already rounds to the Decimal context - so this only decides how those digits
    are written: scientific notation past the chosen size, and the thousands
    separator. Anything that is not a number - every error message the engine can
    raise - comes back untouched, so this never hides what went wrong.
    """

    try:
        value = Decimal(answer)
    except (InvalidOperation, ValueError):
        return answer
    if not value.is_finite():
        return answer

    if value == 0:
        # Both "-0" and a "-0.000" that rounded away read as plain zero.
        return "0"

    threshold = precision.sci_threshold
    if threshold is not None:
        adjusted = value.adjusted()
        if adjusted >= threshold or adjusted <= -threshold:
            # An exponent has no integer part to group, so a scientific-notation
            # answer keeps its digits to themselves.
            return format(value.normalize(), "E")

    if value == value.to_integral_value():
        return apply_grouping(format(value, "f"), precision.grouping)
    return apply_grouping(format(value.normalize(), "f"), precision.grouping)
