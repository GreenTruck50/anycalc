"""
pi.py

Fast π computation using Chudnovsky + Binary Splitting.

gmpy2 (mpz / isqrt) makes it fast and the desktop install gets it through the
[pi] extra, but it is a C extension with no Android wheel, so it is deliberately
not a dependency of the app: without it the same algorithm runs on plain Python
integers, which is the path a phone takes.
"""

import math
import sys
from decimal import Decimal, InvalidOperation
from time import time
from typing import Callable, Optional

try:
    from gmpy2 import mpz, isqrt
except ImportError:
    # The mobile artifact - and any host that did not install the [pi] extra - has
    # no gmpy2, so the same algorithm runs on stdlib integers: slower, but the app
    # works everywhere.
    mpz = int
    isqrt = math.isqrt

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Turning a huge integer into a string is what shows the digits, and CPython
# refuses past 4300 digits unless the guard is lifted. Any real digit count needs
# it, so lifting it is part of importing this module.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


class PiCancelled(Exception):
    """Raised out of :func:`pi_chudnovsky` when a run is asked to stop."""


def pi_chudnovsky(
    digits: int,
    show_progress: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> mpz:
    """
    Compute floor(π * 10**digits) using Chudnovsky + Binary Splitting.

    ``progress_callback(terms_done, terms_total)`` is called once per leaf of the
    binary split, which is what a progress bar reads. ``cancel_check()`` is asked
    the same number of times; returning True raises
    :class:`PiCancelled` so a long run can be abandoned mid-way.
    """
    if digits < MIN_PI_DIGITS:
        raise ValueError(f"digits must be at least {MIN_PI_DIGITS}")

    C = 640320
    C3_OVER_24 = C**3 // 24
    N = pi_term_count(digits)

    # Progress tracking
    completed = 0
    total = N  # we count leaves as the main work unit

    pbar = None
    if show_progress and HAS_TQDM:
        pbar = tqdm(total=total, desc="Computing π", unit="term")

    def report():
        nonlocal completed
        if cancel_check is not None and cancel_check():
            raise PiCancelled(f"cancelled after {completed} of {total} terms")
        completed += 1
        if pbar:
            pbar.update(1)
        if progress_callback:
            progress_callback(completed, total)

    def bs(a: int, b: int) -> tuple[mpz, mpz, mpz]:
        if b - a == 1:
            # Leaf node
            if a == 0:
                Pab = Qab = mpz(1)
                Tab = mpz(13591409)
            else:
                Pab = mpz((6 * a - 5) * (2 * a - 1) * (6 * a - 1))
                Qab = mpz(a * a * a * C3_OVER_24)
                Tab = Pab * (13591409 + 545140134 * a)
                if a & 1:
                    Tab = -Tab
            report()
            return Pab, Qab, Tab

        m = (a + b) // 2
        Pam, Qam, Tam = bs(a, m)
        Pmb, Qmb, Tmb = bs(m, b)

        Pab = Pam * Pmb
        Qab = Qam * Qmb
        Tab = Qmb * Tam + Pam * Tmb
        return Pab, Qab, Tab

    # Run binary splitting
    P, Q, T = bs(0, N)

    if pbar:
        pbar.close()

    # Final calculation. ``isqrt`` is an integer floor, so the square root is up
    # to one unit short and the quotient can then land one decimal too low in its
    # last place - it does for about one digit count in sixty (600 is one of them).
    # The tail is therefore computed with GUARD_DECIMALS extra decimals and
    # truncated back. The series is itself good for some twenty-eight decimals past
    # ``digits`` - that is what the "+ 2" terms of :func:`pi_term_count` buy - so
    # the guard costs a little time and no accuracy.
    one_squared = mpz(10) ** (2 * (digits + GUARD_DECIMALS))
    sqrtC = isqrt(10005 * one_squared)
    pi = (Q * 426880 * sqrtC) // T // mpz(10) ** GUARD_DECIMALS

    return pi

# The Chudnovsky constants, and the digits one term of the series buys. A run
# needs about one term per 14.18 digits, which is what the progress bar divides
# its work into - see :func:`pi_term_count`.
C = 640320
C3_OVER_24 = C**3 // 24
DIGITS_PER_TERM = math.log10(C3_OVER_24 / 6 / 2 / 6)

# How far past the requested decimals the final square root is taken. See the note
# in :func:`pi_chudnovsky`: an integer root is up to a unit short, and the guard is
# what stops that unit from reaching the last decimal that gets shown.
GUARD_DECIMALS = 10

# The digit counts the app offers to compute: 3 is the shortest number that still
# reads as pi, 100 000 000 is the ceiling the Pi page's own menu tops out at.
MIN_PI_DIGITS = 3
MAX_PI_DIGITS = 100_000_000
PI_DIGIT_PRESETS = (
    3,
    12,
    100,
    1_000,
    10_000,
    100_000,
    1_000_000,
    10_000_000,
    100_000_000,
)

# What the app installs as its pi before anyone asks for one. Twelve decimals is
# two more than the float the scientific pad used to reach through ``math.pi``,
# and Chudnovsky needs a single term for it, so startup does not wait.
DEFAULT_PROGRAM_DIGITS = 12


def pi_term_count(digits: int) -> int:
    """How many binary-splitting leaves a run of ``digits`` works through.

    That count is the work a progress bar measures, and it is known before the
    first term is evaluated, which is why the bar can show a percentage rather
    than a spinner.
    """

    if digits < MIN_PI_DIGITS:
        raise ValueError(f"a pi needs at least {MIN_PI_DIGITS} digits")
    return int(digits / DIGITS_PER_TERM + 2)


def format_pi_digits(value, digits: int, first_decimals: int) -> str:
    """pi as ``3.`` followed by at most ``first_decimals`` of its decimals.

    ``value`` is pi itself - a ``Decimal``, or the digit string of one - and
    ``digits`` is how many decimals that value is good for. The decimals shown
    are read off that value, never from a float, so the string stays true as far
    as it goes; a value computed for 12 digits can be shown with 8 decimals, and
    one computed for a million is only ever shown as the slice that was asked
    for, with an ellipsis saying more of them exist.
    """

    if digits < MIN_PI_DIGITS:
        raise ValueError(f"a pi needs at least {MIN_PI_DIGITS} digits")

    text = value if isinstance(value, str) else format(Decimal(value), "f")
    whole, _, decimals = text.partition(".")
    decimals = decimals[: max(digits, 0)]
    shown = decimals[:first_decimals] if first_decimals > 0 else ""
    text = f"{whole}.{shown}" if shown else whole
    if len(decimals) > len(shown):
        text += "..."
    return text


def math_pi_text() -> str:
    """The fallback pi: the shortest string that reads back as float ``pi``.

    A run that cannot start - a cancelled one, or an import that found no
    number - leaves the program on this value rather than on nothing. It is the
    decimal expansion of :data:`math.pi`, which is 15 decimals long and is the
    best pi there is until a longer one is computed.
    """

    return format(Decimal(str(math.pi)), "f")


# The one pi the program calculates with. Everything that needs pi - the
# expression engine above all - reads it from here, so a value adopted from the
# Pi page changes every calculation in the app at once.
#
# Until the app computes its own (``pi_value.install_default_pi`` runs while the
# app starts up) this is the expansion of float ``math.pi``, and the digit count
# says how accurate that really is - 15 decimals, not the 12 the app later
# computes, so nothing ever claims more digits than it holds.
_program_pi = Decimal(str(math.pi))
_program_pi_decimals = format(_program_pi, "f").partition(".")[2]
_program_pi_digits = len(_program_pi_decimals)


def program_pi() -> Decimal:
    """The pi the program calculates with."""

    return _program_pi


def program_pi_digits() -> int:
    """How many decimal places :func:`program_pi` is accurate to."""

    return _program_pi_digits


def program_pi_text() -> str:
    """The program's pi as plain digits, for the status line and dialogs."""

    return f"3.{_program_pi_decimals}"


def program_pi_decimals() -> str:
    """The program's pi decimals alone - the digits after the point."""

    return _program_pi_decimals


def set_program_pi(value, digits: int, decimals: Optional[str] = None) -> None:
    """Make ``value`` the pi the program calculates with.

    This is the one place the program's pi changes. All three arguments are
    checked: the digit count has to be one the app offers to compute, the value
    has to be a finite ``Decimal`` that really is pi, and ``decimals`` - the
    digits to display, when a run has them - has to match that value. A
    half-finished or corrupt run therefore cannot become what every calculation
    multiplies by.
    """

    global _program_pi, _program_pi_digits, _program_pi_decimals

    if not isinstance(digits, int) or isinstance(digits, bool):
        raise ValueError(f"a pi needs a whole number of digits, not {digits!r}")
    if not MIN_PI_DIGITS <= digits <= MAX_PI_DIGITS:
        raise ValueError(
            f"a pi needs between {MIN_PI_DIGITS} and {MAX_PI_DIGITS} digits, "
            f"not {digits}"
        )

    if isinstance(value, Decimal):
        number = value
    else:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{value!r} is not a number")

    if not number.is_finite():
        raise ValueError(f"{value!r} is not a finite number")
    if not (Decimal(3) <= number < Decimal(4)):
        raise ValueError(f"{format(number, 'f')} is not pi")

    if decimals is None:
        # Nothing to reconcile - the digits come from the value itself.
        digits_text = format(number, "f").partition(".")[2]
    else:
        # A finished run hands over both. They have to agree, and checking that
        # is cheap: the digits spell a number, and that number has to be the one
        # that was handed over. Going the other way - printing the value to
        # compare - would stringify a pi of millions of digits for nothing.
        digits_text = decimals
        if Decimal(f"3.{decimals}") != number:
            raise ValueError(
                "the digits handed over are not the value handed over"
            )

    _program_pi = number
    _program_pi_digits = digits
    _program_pi_decimals = digits_text


def main():
    digits = 10_000_000

    if len(sys.argv) > 1:
        try:
            digits = int(sys.argv[1].replace(",", "").replace("_", ""))
        except ValueError:
            print("Usage: python pi.py [digits]")
            sys.exit(1)

    print(f"Target: {digits:,} digits of π\n")
    start = time()

    pi = pi_chudnovsky(digits, show_progress=True)

    elapsed = time() - start
    pi_str = str(pi)

    print(f"\nFinished in {elapsed:.2f} seconds")
    print(f"π ≈ {pi_str[:60]} ... {pi_str[-30:]}")
    print(f"Total digits: {len(pi_str):,}")

if __name__ == "__main__":
    main()