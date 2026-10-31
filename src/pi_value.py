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
    cancelled_at: str = ""

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

    The binary split knows what it costs before it evaluates the first term
    (:func:`pi.run_weight`), so a run has a real percentage from the start rather
    than a spinner, and the phase it is in is carried along because a bar alone
    cannot say what the wait is currently doing.
    """

    phase: str
    terms_done: int
    terms_total: int
    digits: int
    fraction: float
    percent: float
    work_done: float
    work_total: float
    work_per_second: float
    terms_per_second: float
    digits_per_second: float
    seconds_left: Optional[float]

    @property
    def estimated_seconds(self) -> Optional[float]:
        """What the whole run is expected to take, so far."""

        if self.work_per_second <= 0:
            return None
        return self.work_total / self.work_per_second

    @property
    def phase_label(self) -> str:
        """What the wait is currently doing, in words the page can print."""

        return {
            pi.PHASE_SPLIT: "the terms of the series and their products",
            pi.PHASE_FINALISING: "the last square root and division",
        }.get(self.phase, self.phase)


def progress_snapshot(digits: int, work: pi.PiWork, elapsed: float) -> PiProgress:
    """The progress of a run at one :class:`pi.PiWork` checkpoint.

    ``work.work_done`` of ``work_total`` is measured cost, not a term count: it
    covers the terms, the products they are combined into and the last square root
    and division, which is why the bar reaches its end when the run does instead of
    while nearly half the wait is still to come.
    """

    total = float(work.work_total)
    done = max(0.0, min(float(work.work_done), total))
    fraction = done / total if total else 1.0
    speed = done / elapsed if elapsed > 0 and done else 0.0
    remaining = total - done

    return PiProgress(
        phase=work.phase,
        terms_done=int(work.terms_done),
        terms_total=int(work.terms_total),
        digits=digits,
        fraction=fraction,
        percent=fraction * 100,
        work_done=done,
        work_total=total,
        work_per_second=speed,
        terms_per_second=(work.terms_done / elapsed) if elapsed > 0 else 0.0,
        # The run's own average: whatever share of the whole cost is done, that
        # share of the decimals is as good as in hand.
        digits_per_second=(digits * fraction / elapsed) if elapsed > 0 else 0.0,
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

    This is a blocking call - the Pi page runs it on a worker thread. Progress is
    reported at every checkpoint of the split - each term, each combination of two
    half-results, each step of the tail - so the page sees a stream and is
    expected to rate-limit what it makes of it. ``cancel_check`` is asked at those
    same checkpoints, so a run can be stopped in any phase, and a run that is
    stopped comes back ``cancelled`` with no digits rather than raising: the caller
    can say where it stopped and keep the pi the program already uses.
    """

    started = monotonic()

    def report(work: pi.PiWork) -> None:
        if on_progress is not None:
            on_progress(progress_snapshot(digits, work, monotonic() - started))

    try:
        integer = pi.pi_chudnovsky(
            digits, progress_callback=report, cancel_check=cancel_check
        )
    except pi.PiCancelled as error:
        return PiComputation(
            value=None,
            digits=digits,
            seconds=monotonic() - started,
            cancelled=True,
            cancelled_at=str(error),
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
