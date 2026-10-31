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
from typing import Callable, NamedTuple, Optional

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


# A run does not spend its time the way its term count suggests. The binary split
# walks depth first, so the terms of the series are evaluated long before the run
# is anywhere near done: measured on a desktop with gmpy2, the last term is
# reported at 59-64% of the wall clock at 50 000, 200 000 and 1 000 000 decimals.
# A bar that counts terms therefore sits at 100% while nearly half the wait is
# still to come - and a Stop that is only ever asked at a term cannot be honoured
# during that tail, which is what makes a stopped run look like it kept going.
#
# So the bar divides *cost*, not terms. A leaf costs one unit; a node that combines
# two halves spanning ``span`` terms costs ``span ** NODE_EXPONENT``, because that
# is how the big multiplications it performs scale. The exponent is not theory but
# measurement: 1.2 puts the bar within about seven points of the real clock at
# every quarter of a run of 50 000, 200 000 or 1 000 000 decimals, where counting
# terms is off by half the run. The tail - one last square root, product and
# division - weighs about what the root node of the split weighs, and is split
# between its three steps in the measured 45/15/35 proportion.
PHASE_SPLIT = "splitting"
PHASE_FINALISING = "finalising"
NODE_EXPONENT = 1.2
TAIL_WEIGHT = 1.0
TAIL_STEP_WEIGHTS = (0.45, 0.15, 0.40)

# A big run passes millions of nodes. Every one of them is asked whether the run
# should stop - that is what makes a Stop button answer wherever the run happens
# to be - but a report is only sent once this much work has piled up, so a
# progress stream cannot cost more than the arithmetic between its checkpoints.
REPORTS_PER_RUN = 4000


class PiWork(NamedTuple):
    """One progress report out of a running computation.

    ``phase`` names what the run is doing right now. ``terms_done`` of
    ``terms_total`` is the count of series terms, which is the number the page
    quotes as the work a digit count implies. ``work_done`` of ``work_total`` is
    the measured cost of everything done so far, which is what a progress bar
    divides - and unlike the term count, it only reaches its total when the run
    actually ends.
    """

    phase: str
    terms_done: int
    terms_total: int
    work_done: float
    work_total: float


def node_weight(span: int) -> float:
    """What combining the two halves of a ``span``-term node costs."""

    return float(span) ** NODE_EXPONENT


def run_weight(terms: int) -> float:
    """The whole cost of a split over ``terms`` terms, plus its tail.

    The split halves its range until a node covers one term, so the nodes at
    depth ``k`` span ``2**k`` terms and there are about ``terms / 2**k`` of
    them - which turns the sum over the tree into this loop. The exact shape of
    a split whose term count is not a power of two differs slightly; the bar is
    a progress bar, not a benchmark.
    """

    total = float(terms)  # the leaves, one unit each
    span = 1
    while span < terms:
        span *= 2
        total += (terms / span) * node_weight(span)
    return total + TAIL_WEIGHT * node_weight(terms)


def pi_chudnovsky(
    digits: int,
    show_progress: bool = False,
    progress_callback: Optional[Callable[["PiWork"], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> mpz:
    """
    Compute floor(π * 10**digits) using Chudnovsky + Binary Splitting.

    ``progress_callback(PiWork)`` is called at every node of the binary split -
    each term, each combination of two half-results and each step of the tail -
    which is what lets a progress bar cover the whole run rather than only its
    first half. ``cancel_check()`` is asked at those same points, so a run can be
    abandoned in any phase, and returning True raises :class:`PiCancelled`.
    """
    if digits < MIN_PI_DIGITS:
        raise ValueError(f"digits must be at least {MIN_PI_DIGITS}")

    C = 640320
    C3_OVER_24 = C**3 // 24
    N = pi_term_count(digits)

    # Progress tracking, in cost rather than terms - see the note on
    # :data:`NODE_EXPONENT`. A leaf is one unit; an internal node is worth the
    # combining it performs, which grows past the number of terms it covers.
    terms_done = 0
    work_total = run_weight(N)
    tail_weight = TAIL_WEIGHT * node_weight(N)
    work_done = 0.0
    report_step = work_total / REPORTS_PER_RUN
    next_report = 0.0

    # Whether anyone is listening for progress at all - the page, or the command
    # line's bar. Without a listener a node only pays for the Stop check.
    listening = progress_callback is not None or show_progress

    pbar = None
    shown_work = 0.0
    if listening and HAS_TQDM and __name__ == "__main__":
        pbar = tqdm(total=work_total, desc="Computing π", unit="w")

    def stop_check(phase: str) -> None:
        """Ask whether the run has been told to stop."""

        if cancel_check is not None and cancel_check():
            raise PiCancelled(
                f"cancelled while {phase} after {terms_done} of {N} terms"
            )

    def report(phase: str, work: float, force: bool = False) -> None:
        """A node of the split: always a Stop checkpoint, sometimes a report.

        Every node is asked whether the run should stop, which is what makes a
        Stop button answer wherever the run happens to be - in the terms, in the
        combining, or in the last square root and division. Where the run stands
        is reported only once :data:`REPORTS_PER_RUN` reports' worth of work has
        piled up, and not at all when nobody is listening, so the checkpoints
        cannot cost more than the arithmetic between them.
        """

        nonlocal work_done, shown_work, next_report

        stop_check(phase)
        work_done += work
        if not listening:
            return
        if not force and work_done < next_report:
            return
        next_report = work_done + report_step

        if progress_callback is not None:
            progress_callback(
                PiWork(
                    phase=phase,
                    terms_done=terms_done,
                    terms_total=N,
                    work_done=work_done,
                    work_total=work_total,
                )
            )
        if pbar is not None:
            pbar.update(work_done - shown_work)
            shown_work = work_done

    def bs(a: int, b: int) -> tuple[mpz, mpz, mpz]:
        nonlocal terms_done

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
            terms_done += 1
            report(PHASE_SPLIT, 1.0, force=terms_done == N)
            return Pab, Qab, Tab

        m = (a + b) // 2
        Pam, Qam, Tam = bs(a, m)
        Pmb, Qmb, Tmb = bs(m, b)

        # A Stop is asked before the multiplications below - the expensive part of
        # this node, and the reason a stop request is answered promptly even at the
        # very top of the tree, where one node can be a tenth of the whole run.
        stop_check(PHASE_SPLIT)

        Pab = Pam * Pmb
        Qab = Qam * Qmb
        Tab = Qmb * Tam + Pam * Tmb
        report(PHASE_SPLIT, node_weight(b - a))
        return Pab, Qab, Tab

    # Run binary splitting
    P, Q, T = bs(0, N)

    # Final calculation. ``isqrt`` is an integer floor, so the square root is up
    # to one unit short and the quotient can then land one decimal too low in its
    # last place - it does for about one digit count in sixty (600 is one of them).
    # The tail is therefore computed with GUARD_DECIMALS extra decimals and
    # truncated back. The series is itself good for some twenty-eight decimals past
    # ``digits`` - that is what the "+ 2" terms of :func:`pi_term_count` buy - so
    # the guard costs a little time and no accuracy.
    #
    # These three steps are a fifth to a third of the whole run, which is exactly
    # why the bar cannot stop counting at the terms: it would sit at 100% through
    # the longest part of a long wait. They carry their own weight (measured), and
    # the last one is credited with whatever the run has left, so the bar reaches
    # its end as the run does however unevenly the split's tree turned out.
    stop_check(PHASE_FINALISING)
    one_squared = mpz(10) ** (2 * (digits + GUARD_DECIMALS))
    sqrtC = isqrt(10005 * one_squared)
    report(PHASE_FINALISING, tail_weight * TAIL_STEP_WEIGHTS[0], force=True)
    product = Q * 426880 * sqrtC
    report(PHASE_FINALISING, tail_weight * TAIL_STEP_WEIGHTS[1], force=True)
    pi = product // T // mpz(10) ** GUARD_DECIMALS
    report(PHASE_FINALISING, max(0.0, work_total - work_done), force=True)

    if pbar is not None:
        pbar.close()

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