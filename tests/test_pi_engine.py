"""Engine tests for the pi computation - no window, no app host.

``pi.py`` (Chudnovsky + binary splitting), ``pi_value.py`` (a run packaged for
the page) and the pi the program calculates with are all importable without
Flet, so they are tested under bare pytest here. The digit truth for small runs
is spelled out; the big run is checked against MPFR, which computes pi by its own
algorithm - a second opinion, not the same code twice.
"""

import math
from decimal import Decimal

import gmpy2
import pytest

import pi
import pi_value
from calculate import calculate
from config import DECIMAL_PRECISION

# The first 60 decimals of pi, written out rather than computed, so the small runs
# have a truth that does not come from this repository.
PI_DECIMALS = "1415926535897932384626433832795028841971693993751058209749445923"


def mpfr_pi_decimals(decimals: int) -> str:
    """The first ``decimals`` decimals of pi, from MPFR's own pi."""

    value = gmpy2.const_pi(int(decimals * 3.3219280948873626) + 64)
    digits, _, _ = gmpy2.digits(value, 10)
    return digits[: decimals + 1][1:]


# --- the algorithm itself ----------------------------------------------------

@pytest.mark.parametrize("decimals", [3, 12, 50, 100, 1000])
def test_a_run_returns_exactly_the_requested_decimals(decimals: int) -> None:
    """A run of n decimals is n decimals long and reads as pi."""

    integer = pi.pi_chudnovsky(decimals)
    text = str(integer)
    assert len(text) == decimals + 1, "one digit for the whole part, then the run"
    assert text[0] == "3"
    assert text[1:] == PI_DECIMALS[:decimals] or decimals > len(PI_DECIMALS)


@pytest.mark.parametrize("decimals", [166, 244, 306, 359, 360, 600, 1000, 3000])
def test_the_last_decimal_of_a_run_is_not_one_too_low(decimals: int) -> None:
    """The tail of a run is exact, not a unit short.

    ``isqrt`` floors the square root the series is divided by, so the quotient can
    land one unit below pi in its last place. It did for roughly one digit count in
    sixty - the counts below are the ones measured to be off before the run grew
    guard decimals, and 600 is one of them. Every one of them is now checked
    decimal for decimal against MPFR.
    """

    assert str(pi.pi_chudnovsky(decimals))[1:] == mpfr_pi_decimals(decimals)


def test_a_hundred_thousand_digits_match_mpfr() -> None:
    """The binary split agrees with MPFR deep into the number.

    100 000 decimals is well past any constant that could have been typed in by
    hand, and MPFR reaches pi by a completely different route (the agm), so the
    two agreeing is a real check of the algorithm and not of a copy.
    """

    digits = 100_000
    assert str(pi.pi_chudnovsky(digits))[1:] == mpfr_pi_decimals(digits)


def test_half_a_million_digits_match_mpfr() -> None:
    """The page's own scale, checked end to end through :func:`pi_value.compute_pi`.

    This is the run the Pi page offers (the menu tops out at 100 million), driven
    through the wrapper the page actually calls: the decimals have to arrive
    intact, the value they spell has to be the value handed over, and the progress
    reporting has to cover the whole run. It costs a few seconds - it is the test
    that proves the app's headline feature.
    """

    digits = 500_000
    seen: list[pi_value.PiProgress] = []

    computation = pi_value.compute_pi(digits, on_progress=seen.append)

    assert computation.complete
    assert computation.digits == digits
    assert len(computation.decimals) == digits
    assert computation.decimals == mpfr_pi_decimals(digits)

    # The value and the digits are two spellings of the same number, which is the
    # invariant the program relies on when it adopts a run.
    assert Decimal(f"3.{computation.decimals}") == computation.value
    assert computation.text() == f"3.{computation.decimals}"

    # Progress covered the whole run: it started near zero, never went backwards
    # and finished complete.
    assert seen, "a run of half a million decimals reported no progress at all"
    assert seen[0].terms_done >= 1
    steps = [(earlier, later) for earlier, later in zip(seen, seen[1:])]
    assert all(later.fraction >= earlier.fraction for earlier, later in steps)
    assert seen[-1].fraction == pytest.approx(1.0)
    assert all(progress.terms_total == pi.pi_term_count(digits) for progress in seen)

# --- what the progress reporting tells the page ------------------------------

def test_the_same_run_works_without_gmpy2(monkeypatch: pytest.MonkeyPatch) -> None:
    """The path a phone takes: stdlib integers instead of gmpy2's mpz.

    ``pi.py`` binds ``mpz`` / ``isqrt`` at import time and reaches them through the
    module globals, so replacing them with ``int`` and ``math.isqrt`` - the state of
    a mobile artifact, where gmpy2 cannot be packaged at all - has to produce the
    very same digits, through the wrapper the page calls as well as directly.
    """

    monkeypatch.setattr(pi, "mpz", int)
    monkeypatch.setattr(pi, "isqrt", math.isqrt)

    digits = 1_000
    text = str(pi.pi_chudnovsky(digits))
    assert len(text) == digits + 1
    assert text == "3" + mpfr_pi_decimals(digits)

    computation = pi_value.compute_pi(200)
    assert computation.complete
    assert computation.decimals == mpfr_pi_decimals(200)

def test_progress_snapshot_carries_percentage_speed_and_an_estimate() -> None:
    """The bar's numbers come from the term count, not from a guess."""

    total = pi.pi_term_count(10_000)
    done = total // 4
    progress = pi_value.progress_snapshot(10_000, done, total, elapsed=2.0)

    assert progress.fraction == pytest.approx(done / total)
    assert progress.percent == pytest.approx(done / total * 100)
    assert progress.terms_per_second == pytest.approx(done / 2.0)
    assert progress.digits_per_second == pytest.approx(done / 2.0 * pi.DIGITS_PER_TERM)
    # A quarter of the way in after 2 s, the whole run reads as about four times
    # that - and three quarters of it are still ahead.
    assert progress.estimated_seconds == pytest.approx(8.0, rel=0.02)
    assert progress.seconds_left == pytest.approx(6.0, rel=0.02)
    assert progress.terms_total == total
    assert progress.digits == 10_000


def test_progress_before_the_first_term_has_no_speed_to_show() -> None:
    """No terms yet means no rate, and the page prints "-" rather than a guess."""

    progress = pi_value.progress_snapshot(1_000, 0, 75, elapsed=0.0)
    assert progress.fraction == 0.0
    assert progress.terms_per_second == 0.0
    assert progress.seconds_left is None
    assert progress.estimated_seconds is None
    assert pi_value.format_duration(progress.seconds_left) == "-"


def test_the_term_count_is_known_before_a_run_starts() -> None:
    """The bar can show a percentage because the work is counted up front."""

    for digits in (3, 12, 1_000, 500_000, 100_000_000):
        assert pi.pi_term_count(digits) >= 1
    assert pi.pi_term_count(1_000) < pi.pi_term_count(1_000_000)
    # One term buys about 14.18 decimals, which is what the count divides by.
    assert pi.pi_term_count(1418) == pytest.approx(100, abs=3)


def test_a_run_can_be_stopped_between_terms() -> None:
    """Stop works on a real run: it comes back cancelled, with no digits."""

    asked = []

    def cancel_after_three_terms() -> bool:
        asked.append(1)
        return len(asked) > 3

    computation = pi_value.compute_pi(100_000, cancel_check=cancel_after_three_terms)

    assert computation.cancelled
    assert not computation.complete
    assert computation.value is None
    assert computation.decimals == ""
    assert computation.seconds >= 0.0


def test_stopping_a_run_leaves_the_programs_pi_alone() -> None:
    """A cancelled run cannot reach the value every calculation multiplies by."""

    before = pi.program_pi_text()
    computation = pi_value.compute_pi(50_000, cancel_check=lambda: True)
    assert computation.cancelled

    with pytest.raises(ValueError, match="cancelled run"):
        pi_value.adopt(computation)
    assert pi.program_pi_text() == before


# --- the menu's range --------------------------------------------------------

def test_the_page_offers_three_decimals_up_to_a_hundred_million() -> None:
    """The 3 - 100 000 000 range the feature asks for, and its presets."""

    assert pi.MIN_PI_DIGITS == 3
    assert pi.MAX_PI_DIGITS == 100_000_000
    assert pi.PI_DIGIT_PRESETS[0] == pi.MIN_PI_DIGITS
    assert pi.PI_DIGIT_PRESETS[-1] == pi.MAX_PI_DIGITS
    assert list(pi.PI_DIGIT_PRESETS) == sorted(pi.PI_DIGIT_PRESETS)

    with pytest.raises(ValueError, match="at least 3"):
        pi.pi_chudnovsky(2)
    with pytest.raises(ValueError, match="at least 3"):
        pi.pi_term_count(2)


def test_the_program_rejects_a_pi_outside_the_offered_range() -> None:
    for bad_digits in (2, 100_000_001, 0, -5, "12", 1.5, True):
        with pytest.raises(ValueError):
            pi.set_program_pi(Decimal("3.1415926535"), bad_digits)


def test_the_program_rejects_a_value_that_is_not_pi() -> None:
    for bad_value in (Decimal("2.1415926535"), Decimal("4.1415926535"),
                      Decimal("nan"), Decimal("Infinity"), "not a number"):
        with pytest.raises(ValueError):
            pi.set_program_pi(bad_value, 12)


def test_the_program_rejects_digits_that_disagree_with_the_value() -> None:
    """The two spellings handed over by a run have to be the same number."""

    with pytest.raises(ValueError, match="not the value handed over"):
        pi.set_program_pi(Decimal("3.141592653589"), 12, "141592653588")


# --- the pi the whole program uses -------------------------------------------

@pytest.fixture(autouse=True)
def restore_program_pi():
    """Every test leaves the program's pi exactly as it found it."""

    before = (pi.program_pi(), pi.program_pi_digits(), pi.program_pi_decimals())
    yield
    pi.set_program_pi(*before)


def test_the_app_starts_on_a_pi_it_computed_itself() -> None:
    """Twelve decimals from the Chudnovsky series, not the float ``math.pi``."""

    computation = pi_value.install_default_pi()

    assert computation.digits == pi.DEFAULT_PROGRAM_DIGITS == 12
    assert computation.complete
    assert pi.program_pi_digits() == 12
    assert pi.program_pi_text() == f"3.{PI_DECIMALS[:12]}"
    assert pi.program_pi_decimals() == PI_DECIMALS[:12]
    assert pi.program_pi() == Decimal("3.141592653589")


def test_a_finished_run_becomes_the_pi_every_calculation_uses() -> None:
    """Adopting a longer pi is what makes the pads calculate with more digits."""

    computation = pi_value.compute_pi(100)
    pi_value.adopt(computation)

    assert pi.program_pi_digits() == 100
    assert pi.program_pi() == computation.value
    assert pi.program_pi_decimals() == computation.decimals

    doubled = calculate("pi + pi", scientific=True)
    # The engine works in a 50-digit Decimal context, so the answer is compared
    # well inside that - the point is that pi now carries far more decimals than
    # the 15 a float ever gave.
    expected = format(Decimal(2) * Decimal(f"3.{PI_DECIMALS}"), "f")
    assert doubled[:47] == expected[:47]
    assert doubled.startswith("6.283185307179586476925286766559")


def test_the_calculators_pi_is_the_program_pi() -> None:
    """``pi`` on either pad is :func:`pi.program_pi`, digit for digit."""

    assert calculate("pi", scientific=True) == format(pi.program_pi(), "f")


def test_a_caller_can_hand_the_engine_its_own_pi() -> None:
    """The seam the page-less tests use to prove the engine reaches for the value."""

    got = calculate("pi * 2", scientific=True, pi_provider=lambda: Decimal("3.5"))
    assert got == "7"


def test_a_provider_that_hands_over_nothing_falls_back_to_the_program_pi() -> None:
    got = calculate("pi", scientific=True, pi_provider=lambda: None)
    assert got == format(pi.program_pi(), "f")


# --- showing a pi that is far too long for one text control ------------------

def test_a_shown_pi_is_cut_to_the_decimals_that_were_asked_for() -> None:
    shown = pi.format_pi_digits(f"3.{PI_DECIMALS}", len(PI_DECIMALS), 20)
    assert shown == f"3.{PI_DECIMALS[:20]}..."

    whole = pi.format_pi_digits(f"3.{PI_DECIMALS}", len(PI_DECIMALS), len(PI_DECIMALS))
    assert whole == f"3.{PI_DECIMALS}", "nothing hidden, so no ellipsis"

    # Asking for no decimals at all still says the number continues.
    assert pi.format_pi_digits("3.141592653589", 12, 0) == "3..."


def test_a_shown_pi_never_shows_more_than_the_run_produced() -> None:
    """A 12-decimal pi stays 12 decimals long however wide the request is."""

    assert pi.format_pi_digits("3.141592653589", 12, 500) == "3.141592653589"
    # The 64 spelled-out decimals are only ever shown as far as they were asked
    # for: a run of 12 cannot be shown with 20.
    assert pi.format_pi_digits(f"3.{PI_DECIMALS}", 12, 20) == "3.141592653589"


def test_the_fallback_pi_is_the_float_expansion() -> None:
    """The pi used before any run - and by a run that cannot start."""

    assert pi.math_pi_text() == format(Decimal(str(math.pi)), "f")
    assert pi.math_pi_text().startswith("3.14159265358979")


def test_the_fallback_pi_claims_only_the_decimals_it_holds() -> None:
    """The module-level pi is the float, and says 15 - not the 12 it later computes.

    Nothing in the app may claim more digits than it actually has: the page shows
    this count next to the value until a run replaces it.
    """

    assert pi.program_pi_text() == pi.math_pi_text()
    assert pi.program_pi_digits() == len(pi.program_pi_decimals()) == 15


def test_a_calculation_reaches_the_programs_pi_only_as_far_as_the_engine_goes() -> None:
    """The 50-digit Decimal context is the ceiling, not the 100 digits computed.

    Adopting a longer pi does make the pads calculate with it - but every
    expression is evaluated at ``DECIMAL_PRECISION`` significant digits, so a
    hundred-decimal pi shows through as fifty. That is the calculator's own
    precision, and it is what the spec states.
    """

    pi_value.adopt(pi_value.compute_pi(100))
    shown = calculate("pi", scientific=True)

    significant = len(shown.replace(".", "").lstrip("0"))
    assert significant == DECIMAL_PRECISION
    assert shown == f"3.{PI_DECIMALS[: DECIMAL_PRECISION - 1]}"


def test_a_computation_can_be_shown_as_a_leading_slice() -> None:
    computation = pi_value.compute_pi(100)
    assert computation.format(50) == f"3.{computation.decimals[:50]}..."
    assert computation.format(100) == f"3.{computation.decimals}"

