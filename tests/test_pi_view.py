"""The pi page without a window: the form rules and the lazy digits dialog.

``pi_view.py`` builds Flet controls but needs no app host, so the page logic that
a UI test cannot reach - the page sits below the drawer's fold, and the test host
has neither scroll nor drag (see the skip in ``tests/test_app.py``) - is driven
here against a stub page. What gets pinned is the behaviour the page promises:

* a digit count is only accepted inside the range the app offers, and the typed
  field wins over the menu;
* a finished run can be adopted, and the program's pi is what it became;
* a stopped run adopts nothing and leaves the program's pi alone;
* the digits dialog starts with a few lines and only grows as the reader scrolls
  near its bottom, and never builds more lines than the digits need - which is
  what keeps a run of a hundred million decimals from ever being on screen at
  once.
"""

import threading
import time
from types import SimpleNamespace
from typing import Callable

import flet as ft
import pytest

import pi
import pi_value
from calculate import calculate
from config import DECIMAL_PRECISION
from pi_view import (
    DIALOG_CHUNK_LINES,
    DIALOG_FILL_AHEAD_LINES,
    DIALOG_INDEX_GUTTER,
    DIALOG_INITIAL_LINES,
    DIALOG_LINE_DIGITS,
    DIALOG_LINE_HEIGHT,
    PiView,
    percent_text,
)

PI_DECIMALS = (
    # 600 decimals, spelled out here rather than computed, so the page is
    # checked against a truth that does not come from this repository.
    "141592653589793238462643383279502884197169399375105820974944"
    "592307816406286208998628034825342117067982148086513282306647"
    "093844609550582231725359408128481117450284102701938521105559"
    "644622948954930381964428810975665933446128475648233786783165"
    "271201909145648566923460348610454326648213393607260249141273"
    "724587006606315588174881520920962829254091715364367892590360"
    "011330530548820466521384146951941511609433057270365759591953"
    "092186117381932611793105118548074462379962749567351885752724"
    "891227938183011949129833673362440656643086021394946395224737"
    "190702179860943702770539217176293176752384674818467669405132"
)


class StubPage:
    """Just enough of a page for the view: it updates, and it opens dialogs."""

    def __init__(self) -> None:
        self.updates = 0
        self.dialogs: list[ft.AlertDialog] = []
        self.popped = 0
        # What the app's shared copy-button factory was handed to copy, in order.
        self.copies: list[Callable[[], str]] = []

    def update(self) -> None:
        self.updates += 1

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        self.popped += 1

    def run_thread(self, handler: Callable[..., object], *args: object) -> None:
        """Stand in for ``Page.run_thread``, which the page starts its compute on."""

        threading.Thread(target=handler, args=args, daemon=True).start()

    def make_copy_button(
        self, value: Callable[[], str], tooltip: str = ""
    ) -> ft.IconButton:
        """Stand in for ``Clipboard.make_button``, keeping the callable it was given."""

        self.copies.append(value)
        return ft.IconButton(ft.Icons.COPY, tooltip=tooltip)


@pytest.fixture()
def view() -> PiView:
    """A pi page on a stub page, on the pi the app installs at startup.

    The program's pi is process-wide state, so the fixture installs what
    ``AnycalcApp`` installs when it starts and puts back what it found afterwards.
    """

    before = (pi.program_pi(), pi.program_pi_digits(), pi.program_pi_decimals())
    pi_value.install_default_pi()
    page = StubPage()
    page_view = PiView(page, page.make_copy_button)
    page_view.build()
    try:
        yield page_view
    finally:
        pi.set_program_pi(before[0], before[1], decimals=before[2])


def walk(control):
    """Every control under ``control``, however it is held."""

    yield control
    for name in ("controls", "content", "actions", "title"):
        child = getattr(control, name, None)
        if child is None:
            continue
        children = child if isinstance(child, list) else [child]
        for sub in children:
            yield from walk(sub)


def find_by_key(root, key: str):
    for control in walk(root):
        if getattr(control, "key", None) == key:
            return control
    raise AssertionError(f"no control with key {key!r}")


def find_by_text(root, text: str):
    for control in walk(root):
        if isinstance(control, ft.Text) and control.value == text:
            return control
    return None


def wait_for_run(view: PiView, limit: float = 30.0) -> None:
    """Wait for the worker thread a run started to finish."""

    deadline = time.monotonic() + limit
    while view.running:
        if time.monotonic() > deadline:
            raise AssertionError("the run never finished")
        time.sleep(0.005)


def set_digits(view: PiView, typed: str = "", choice: str = "12") -> None:
    view.digits_field.value = typed
    view.digits_dropdown.value = choice
    view.refresh_plan()


def scrolled(extent_after: float):
    """A scroll notification reporting how much content is still below."""

    return SimpleNamespace(extent_after=extent_after)


def run_to_completion(view: PiView, typed: str) -> None:
    set_digits(view, typed=typed)
    view.start_run()
    wait_for_run(view)


# --- how many digits the form will accept ------------------------------------

def test_the_menu_offers_every_count_the_page_promises(view: PiView) -> None:
    options = [option.key for option in view.digits_dropdown.options]
    assert options == [str(count) for count in pi.PI_DIGIT_PRESETS]
    assert options[0] == "3" and options[-1] == "100000000"


def test_the_page_opens_on_the_pi_the_app_computed_at_startup(view: PiView) -> None:
    page = view.build()
    current = find_by_key(page, "pi-current")
    assert current.value == f"3.{PI_DECIMALS[: pi.DEFAULT_PROGRAM_DIGITS]}"
    note = find_by_key(page, "pi-current-note")
    assert note.value == "12 decimals, computed by this app"


@pytest.mark.parametrize(
    "typed,want_valid",
    [("", True), ("3", True), ("500000", True), ("100000000", True),
     ("2", False), ("100000001", False), ("0", False), ("-7", False),
     ("many", False), ("12_000", True), ("12,000", True)],
)
def test_the_digit_count_is_checked_before_a_run_can_start(
    view: PiView, typed: str, want_valid: bool
) -> None:
    set_digits(view, typed)
    assert view.digits_are_valid(view.requested_digits()) is want_valid
    assert view.compute_button.disabled is not want_valid
    plan = find_by_key(view.build(), "pi-plan")
    if want_valid:
        assert "terms of the Chudnovsky series" in plan.value
    else:
        assert "between 3 and 100,000,000" in plan.value


def test_a_typed_count_beats_the_menu(view: PiView) -> None:
    set_digits(view, typed="500000", choice="12")
    assert view.requested_digits() == 500_000


def test_a_count_the_form_rejects_never_starts_a_thread(view: PiView) -> None:
    set_digits(view, typed="2")
    view.start_run()
    assert view.running is False
    assert view.computation is None


# --- a run, and what it may change -------------------------------------------

def test_a_finished_run_reports_itself_and_arms_the_buttons(view: PiView) -> None:
    run_to_completion(view, "100")
    page = view.build()

    assert view.computation is not None and view.computation.complete
    assert view.progress_bar.value == 1.0
    assert find_by_key(page, "pi-percent").value == "100%"
    assert "100 decimals in" in find_by_key(page, "pi-status").value
    assert "press the button below" in find_by_key(page, "pi-status").value
    assert view.adopt_button.disabled is False
    assert view.view_button.disabled is False
    assert view.stop_button.disabled is True
    assert view.compute_button.disabled is False

    result = find_by_key(page, "pi-result")
    assert result.value == f"3.{view.computation.decimals}"
    assert result.value.startswith(f"3.{PI_DECIMALS[:60]}")


def test_the_progress_card_shows_a_speed_and_a_finished_time(view: PiView) -> None:
    run_to_completion(view, "5000")
    page = view.build()

    terms = find_by_key(page, "pi-terms").value
    speed = find_by_key(page, "pi-speed").value
    estimate = find_by_key(page, "pi-estimate").value
    total = pi.pi_term_count(5_000)
    assert terms == f"{total:,} / {total:,} terms"
    assert speed.startswith("speed ") and speed.endswith(" digits/s")
    assert estimate.startswith("took ")


def test_adopting_makes_the_run_the_pi_every_calculation_uses(view: PiView) -> None:
    run_to_completion(view, "60")
    view.adopt_value()

    assert pi.program_pi_digits() == 60
    assert pi.program_pi_decimals() == PI_DECIMALS[:60]
    assert "60 decimals, computed by this app" in (
        find_by_key(view.build(), "pi-current-note").value
    )
    assert "the program now calculates with pi to 60 decimals" in (
        find_by_key(view.build(), "pi-status").value
    )

    # The pads really do multiply by it - as far as the engine's own 50-digit
    # Decimal context lets a longer pi through.
    shown = f"3.{PI_DECIMALS[: DECIMAL_PRECISION - 1]}"
    assert calculate("pi", scientific=True) == shown


@pytest.mark.parametrize(
    ("percent", "text"),
    [(0.0, "0%"), (7.09e-05, "0%"), (12.34, "12.3%"), (12.0, "12%"), (100.0, "100%")],
)
def test_the_percentage_never_carries_a_pointless_decimal(
    percent: float, text: str
) -> None:
    """``0%`` and ``12%``, not ``0.0%`` and ``12.0%``."""

    assert percent_text(percent) == text


def test_a_stopped_run_adopts_nothing_and_says_so(view: PiView) -> None:
    before = (pi.program_pi(), pi.program_pi_digits(), pi.program_pi_decimals())

    set_digits(view, typed="200000")
    view.start_run()
    # The Stop button, pressed a moment after Compute: the worker is asked before
    # its next term and comes back with nothing.
    view.stop_run()
    wait_for_run(view)

    page = view.build()
    assert view.computation is not None and view.computation.cancelled
    assert view.adopt_button.disabled is True
    assert view.view_button.disabled is True
    assert find_by_key(page, "pi-percent").value == "0%"
    # A stopped run leaves the bar where the terms left it - a hair past zero,
    # never a finished bar - and the percentage still reads 0%.
    assert 0.0 <= view.progress_bar.value < 0.01
    assert "the program still uses its previous pi" in (
        find_by_key(page, "pi-status").value
    )

    # Even called directly, a cancelled run cannot change the program's pi.
    view.adopt_value()
    assert (pi.program_pi(), pi.program_pi_digits(), pi.program_pi_decimals()) == before


# --- the digits dialog, filled as the reader scrolls -------------------------

def open_dialog_after_a_run(view: PiView, typed: str = "600") -> ft.ListView:
    """Finish a run, press "View digits", and hand back the dialog's list."""

    run_to_completion(view, typed)
    view.open_digits()
    assert len(view.page.dialogs) == 1
    dialog = view.page.dialogs[-1]
    assert dialog.modal is True
    return find_by_key(dialog, "pi-digits-list")


def line_digits(control: ft.Text) -> str:
    """The decimals one dialog line holds, without its index gutter."""

    return control.value[DIALOG_INDEX_GUTTER + 2:]


def line_index(control: ft.Text) -> int:
    """Which decimal a dialog line starts at, as the gutter says."""

    return int(control.value[:DIALOG_INDEX_GUTTER])


def digits_on_screen(lines: ft.ListView) -> str:
    """The decimals the built lines hold, concatenated."""

    return "".join(line_digits(control) for control in lines.controls)


def test_the_dialog_starts_with_only_a_few_lines(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "3000")

    # 3000 decimals are fifty lines, but only the first screenful is built at all
    # until the reader scrolls.
    assert len(lines.controls) == DIALOG_INITIAL_LINES < -(-3000 // DIALOG_LINE_DIGITS)
    # A fixed extent is what lets Flutter render only the lines in the viewport,
    # however many lines the list ends up holding.
    assert lines.item_extent == DIALOG_LINE_HEIGHT
    assert lines.build_controls_on_demand is True

    first, second = lines.controls[0], lines.controls[1]
    assert line_index(first) == 1 and line_index(second) == 1 + DIALOG_LINE_DIGITS
    assert line_digits(first) == PI_DECIMALS[:DIALOG_LINE_DIGITS]
    second_line = PI_DECIMALS[DIALOG_LINE_DIGITS : 2 * DIALOG_LINE_DIGITS]
    assert line_digits(second) == second_line


def test_scrolling_near_the_bottom_adds_the_next_batch(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "600")
    before = len(lines.controls)

    view._fill_more_on_scroll(scrolled(extent_after=0.0))

    # 600 decimals fill exactly ten lines of 60, all of which the dialog built
    # already: the list may never grow past the digits that were computed.
    assert digits_on_screen(lines) == view.computation.decimals
    assert len(lines.controls) == before
    assert view._dialog_shown == -(-600 // DIALOG_LINE_DIGITS)


def test_a_run_far_longer_than_the_first_screen_fills_in_batches(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "10000")
    total_lines = -(-10000 // DIALOG_LINE_DIGITS)
    assert total_lines > DIALOG_INITIAL_LINES

    assert len(lines.controls) == DIALOG_INITIAL_LINES
    view._fill_more_on_scroll(scrolled(extent_after=0.0))
    assert len(lines.controls) == DIALOG_INITIAL_LINES + DIALOG_CHUNK_LINES

    for _ in range(30):
        view._fill_more_on_scroll(scrolled(extent_after=0.0))
    assert len(lines.controls) == total_lines
    assert digits_on_screen(lines) == view.computation.decimals

    # Once the number is on screen, scrolling does not keep building.
    view._fill_more_on_scroll(scrolled(extent_after=0.0))
    assert len(lines.controls) == total_lines


def test_the_footline_counts_what_is_on_screen(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "10000")
    shown = DIALOG_INITIAL_LINES * DIALOG_LINE_DIGITS
    assert find_by_text(
        view.page.dialogs[-1],
        f"showing the first {shown:,} of 10,000 decimals - scroll for more",
    ) is not None

    for _ in range(30):
        view._fill_more_on_scroll(scrolled(extent_after=0.0))
    assert (
        find_by_text(view.page.dialogs[-1], "all 10,000 decimals on screen") is not None
    )


def test_scrolling_far_from_the_bottom_adds_nothing(view: PiView) -> None:
    """Reading the top of a long dialog must not load the whole number."""

    lines = open_dialog_after_a_run(view, "10000")
    before = len(lines.controls)
    far_below = (DIALOG_FILL_AHEAD_LINES + 1) * 18
    view._fill_more_on_scroll(scrolled(extent_after=far_below))
    assert len(lines.controls) == before


def test_a_short_run_fits_the_dialog_without_any_scrolling(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "120")
    for _ in range(5):
        view._fill_more_on_scroll(scrolled(extent_after=0.0))
    assert len(lines.controls) == 2, "120 decimals are two lines, never a third"
    assert digits_on_screen(lines) == PI_DECIMALS[:120]


def test_the_programs_own_digits_open_the_same_way(view: PiView) -> None:
    view.open_current_digits()
    dialog = view.page.dialogs[-1]

    assert dialog.title.value == "Pi the program uses - 12 decimals"
    lines = find_by_key(dialog, "pi-digits-list")
    assert len(lines.controls) == 1, "twelve decimals are one line"
    assert digits_on_screen(lines) == PI_DECIMALS[:12]
    assert find_by_text(dialog, "all 12 decimals on screen") is not None


def test_the_close_button_pops_the_dialog(view: PiView) -> None:
    open_dialog_after_a_run(view, "600")
    dialog = view.page.dialogs[-1]
    close = [
        control
        for control in walk(dialog)
        if isinstance(control, ft.TextButton) and control.content == "Close"
    ]
    assert len(close) == 1
    close[0].on_click()
    assert view.page.popped == 1


def test_the_copy_button_of_the_dialog_hands_over_every_digit(view: PiView) -> None:
    open_dialog_after_a_run(view, "600")
    dialog = view.page.dialogs[-1]
    copies = [
        control
        for control in walk(dialog)
        if isinstance(control, ft.IconButton)
    ]
    assert len(copies) == 1
    # The copy button was handed the whole number, not what the dialog happens to
    # have built on screen.
    assert view.page.copies[-1]() == f"3.{PI_DECIMALS[:600]}"
