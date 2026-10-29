"""Run one Chudnovsky computation and hand the result back to the page.

The digit algorithm lives in :mod:`pi`; this module only times a run, keeps the
digits with the count they were asked for, and gives the Pi page a seam for
putting a finished run into the program's pi without reaching into that module
itself.
"""

import dataclasses
from decimal import Decimal
from time import monotonic
from typing import Callable, Optional

import pi


@dataclasses.dataclass(frozen=True)
class PiComputation:
    """What a finished run produced.

    ``value`` is pi itself, good to ``digits`` decimal places, and ``decimals`` is
    the same thing as digits - the decimals after the point, no ``3.`` in front -
    because a page shows a pi as text while the program multiplies by the number.
    """

    value: Optional[Decimal]
    digits: int
    seconds: float
    decimals: str = ""
    cancelled: bool = False

    @property
    def complete(self) -> bool:
        return not self.cancelled and self.value is not None

    def text(self) -> str:
        """The whole computed pi as digits: "3." and every decimal."""

        return f"3.{self.decimals}"

    def format(self, first_decimals: int) -> str:
        """The leading slice of the run, for a card that cannot show millions."""

        return pi.format_pi_digits(self.text(), self.digits, first_decimals)


@dataclasses.dataclass(frozen=True)
class PiProgress:
    """Where a running computation stands, in the numbers the page prints.

    The binary split knows its leaf count before it evaluates the first term
    (:func:`pi.pi_term_count`), so a run has a real percentage from the start
    rather than a spinner - and once a few terms are in, the same count gives a
    speed and therefore a finish time.
    """

    terms_done: int
    terms_total: int
    digits: int
    fraction: float
    percent: float
    terms_per_second: float
    digits_per_second: float
    seconds_left: Optional[float]

    @property
    def estimated_seconds(self) -> Optional[float]:
        """What the whole run is expected to take, so far."""

        if self.terms_per_second <= 0:
            return None
        return self.terms_total / self.terms_per_second


def progress_snapshot(
    digits: int, terms_done: int, terms_total: int, elapsed: float
) -> PiProgress:
    """The progress of a run after ``terms_done`` of ``terms_total`` terms."""

    terms_done = max(0, min(int(terms_done), int(terms_total)))
    fraction = terms_done / terms_total if terms_total else 1.0
    speed = terms_done / elapsed if elapsed > 0 and terms_done else 0.0
    remaining = terms_total - terms_done
    return PiProgress(
        terms_done=terms_done,
        terms_total=int(terms_total),
        digits=digits,
        fraction=fraction,
        percent=fraction * 100,
        terms_per_second=speed,
        digits_per_second=speed * pi.DIGITS_PER_TERM,
        seconds_left=(remaining / speed) if speed > 0 else None,
    )


def format_duration(seconds) -> str:
    """A duration as the page prints it: "0.4 s", "12 s", "3 min 05 s", "1 h 23 min"."""

    if seconds is None:
        return "-"
    total = max(0.0, float(seconds))
    if total < 10:
        return f"{total:.1f} s"
    if total < 60:
        return f"{round(total)} s"
    minutes, secs = divmod(int(round(total)), 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def compute_pi(
    digits: int,
    on_progress: Optional[Callable[[PiProgress], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> PiComputation:
    """Compute ``digits`` decimals of pi, reporting progress as it goes.

    This is a blocking call - the Pi page runs it on a worker thread. A run that
    is asked to stop comes back ``cancelled`` with no digits rather than raising,
    so the caller can tell the user where it stopped and keep the pi the program
    already uses.
    """

    started = monotonic()

    def report(terms_done: int, terms_total: int) -> None:
        if on_progress is not None:
            elapsed = monotonic() - started
            on_progress(progress_snapshot(digits, terms_done, terms_total, elapsed))

    try:
        integer = pi.pi_chudnovsky(
            digits, progress_callback=report, cancel_check=cancel_check
        )
    except pi.PiCancelled:
        return PiComputation(
            value=None, digits=digits, seconds=monotonic() - started, cancelled=True
        )

    # The integer the algorithm returns is pi scaled by 10**digits, so its first
    # digit is the whole part. Reading it as text - never dividing by a power of
    # ten - keeps every digit exact: a Decimal division would round the answer to
    # the 50-digit context the calculator runs in.
    digits_text = str(integer)
    return PiComputation(
        value=Decimal(f"{digits_text[0]}.{digits_text[1:]}"),
        digits=digits,
        seconds=monotonic() - started,
        decimals=digits_text[1:],
    )


def install_default_pi(digits: int = pi.DEFAULT_PROGRAM_DIGITS) -> PiComputation:
    """Compute the pi the app starts with and make it the program's pi.

    The app calls this once while it starts up, so from the first keystroke on
    every calculation uses a pi the program computed itself instead of the
    15-decimal float ``math.pi``.
    """

    computation = compute_pi(digits)
    pi.set_program_pi(computation.value, computation.digits, computation.decimals)
    return computation


def adopt(computation: PiComputation) -> None:
    """Put a finished run into the program - "Use this value for the program"."""

    if not computation.complete:
        raise ValueError("a cancelled run has no value to use")
    pi.set_program_pi(computation.value, computation.digits, computation.decimals)


def calculate_with_pi(expression: str, scientific: bool, provider) -> str:
    """``calculate()`` with a pi supplied by ``provider``.

    The seam the tests use: :func:`calculate_with_program_pi` hands over the
    program's current pi, and a test hands over a known one to check the engine
    really does reach for it.
    """

    import calculate

    def _pi():
        value = provider()
        if value is None:
            return pi.program_pi()
        return value

    return calculate.calculate(expression, scientific, pi_provider=_pi)
