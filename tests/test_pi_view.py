"""The pi page without a window: the form rules and the lazy digits dialog.

``pi_view.py`` builds Flet controls but needs no app host, so the page logic that
a UI test cannot reach - the page sits below the drawer's fold, and the test host
has neither scroll nor drag (see the skip in ``tests/test_app.py``) - is driven
here against a stub page. What gets pinned is the behaviour the page promises:

* a digit count is only accepted inside the range the app offers, and the typed
  field wins over the menu;
* a finished run can be adopted, and the program's pi is what it became;
* a stopped run adopts nothing and leaves the program's pi alone;
* the digits dialog is the plain number in an ordinary scroll area; it holds one
  page of the number at a time and turns pages when asked, so the list never grows
  under the reader's fingers - which is what made its scrollbar lie about how much
  number there was - and a run of a hundred million decimals is never on screen.
"""

import asyncio
import threading
import time
from typing import Callable, Optional
from unittest.mock import patch

import flet as ft
import pytest

import pi
import pi_value
from calculate import calculate
from config import DECIMAL_PRECISION
from pi_view import (
    DIALOG_GLYPH_WIDTH,
    DIALOG_LINE_HEIGHT,
    DIALOG_PAGE_DECIMALS,
    PROGRESS_PAINT_SECONDS,
    PiView,
    dialog_line_digits,
    dialog_page_range,
    dialog_pages,
    dialog_width,
    percent_text,
    precision_notice,
)
from styles import CARD_BACKGROUND

# How many decimals one dialog line holds when the dialog has no window geometry to
# go by - which is the case for every dialog opened in this file.
LINE_DIGITS = dialog_line_digits(None)

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
        # The background work the page was asked to start, in order: a run and the
        # clock that repaints the progress card are two separate pieces of work.
        self.threads: list[Callable[..., object]] = []
        # The coroutines the page was asked to schedule, by name.
        self.tasks: list[str] = []

    def update(self) -> None:
        self.updates += 1

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        self.popped += 1

    def run_thread(self, handler: Callable[..., object], *args: object) -> None:
        """Stand in for ``Page.run_thread``, which the page starts its compute on."""

        self.threads.append(handler)
        threading.Thread(target=handler, args=args, daemon=True).start()

    def run_task(self, handler: Callable[..., object]) -> object:
        """Stand in for ``Page.run_task``, which schedules a coroutine.

        There is no event loop here, so the coroutine is closed rather than awaited -
        the test only cares that the page was asked to schedule it. A token is handed
        back the way a real page hands back the task it created.
        """

        self.tasks.append(getattr(handler, "__name__", str(handler)))
        coroutine = handler()
        if coroutine is not None:
            coroutine.close()
        return f"task:{self.tasks[-1]}"

    def make_copy_button(
        self, value: Callable[[], str], tooltip: str = "", label: Optional[str] = None
    ) -> ft.Control:
        """Stand in for ``Clipboard.make_button``, keeping the callable it was given."""

        self.copies.append(value)
        if label:
            return ft.TextButton(content=label, tooltip=tooltip)
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


def test_the_progress_card_names_the_part_of_the_run_under_way(view: PiView) -> None:
    """A bar that seems to stall needs a line saying what the wait is busy with.

    The products of the terms and the last square root and division outweigh the
    terms themselves and come after them, so a page that only counted terms looked
    finished - or stuck - long before the run was.
    """

    real_compute = pi_value.compute_pi
    in_engine = threading.Event()
    release = threading.Event()

    def hold_in_the_engine(digits, on_progress=None, cancel_check=None):
        in_engine.set()
        release.wait(10.0)
        return real_compute(digits, on_progress=on_progress, cancel_check=cancel_check)

    # Held at the engine's door so the state before the first report can be seen at
    # all: the worker now paints with its first report, which used to be a race.
    with patch.object(pi_value, "compute_pi", new=hold_in_the_engine):
        set_digits(view, typed="200000")
        view.start_run()
        assert in_engine.wait(5.0), "the worker reached the engine"
        assert find_by_key(view.build(), "pi-phase").value == (
            "starting the binary split ..."
        ), "the line beside a 0% bar is never empty"
        release.set()
        wait_for_run(view)

    # What a report puts there is named after the run rather than after the terms, so
    # the tail - the part that outlasts the term count - still says what it is doing.
    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(5000, on_progress=reports.append)
    tail = [
        report
        for report in reports
        if report.phase_label == "the last square root and division"
    ]
    assert tail, "a finished run reports what its own tail was doing"
    view._card_final = False
    view._last_paint = 0.0
    view.progress = tail[0]
    view._paint_progress()
    assert view.phase_text.value == "now: the last square root and division"

    run_to_completion(view, "5000")
    assert find_by_key(view.build(), "pi-phase").value == "done"


def test_the_progress_track_is_a_different_colour_than_its_card(view: PiView) -> None:
    """The unfilled part of the bar has to be visible on the card it sits on."""

    assert view.progress_bar.bgcolor != CARD_BACKGROUND


def test_the_digits_are_plain_text_and_not_a_code_viewer(view: PiView) -> None:
    """The number is being read, not debugged: no gutter, no monospace, no box.

    The dialog used to tag every line with the decimal it starts at and set it in a
    monospace font on a coloured card - a source-code viewer. What was asked for is
    the digits in an ordinary scroll area, so a line holds digits and nothing else.
    """

    lines = open_dialog_after_a_run(view, "600")
    first = lines.controls[0]

    assert first.value == PI_DECIMALS[:LINE_DIGITS]
    assert first.font_family != "monospace"
    assert first.selectable is True
    assert lines.scroll == ft.ScrollMode.AUTO, "an ordinary scrollbar"
    assert all(
        set(control.value) <= set("0123456789") for control in lines.controls
    ), "a line of the dialog is digits, and only digits"


@pytest.mark.parametrize("page_width", [None, 1400, 900, 420, 360, 300, 240])
def test_a_line_never_runs_past_the_dialog_it_is_shown_in(
    page_width: Optional[int]
) -> None:
    """A phone used to cut the tail off every line of a long run.

    The line is measured rather than fixed, so it shortens with the window instead of
    overflowing it.
    """

    digits = dialog_line_digits(page_width)
    assert digits >= 20, "never a line too narrow to read"
    assert digits * DIALOG_GLYPH_WIDTH <= dialog_width(page_width)
    assert digits <= dialog_line_digits(None)


def test_a_phone_gets_a_line_it_can_actually_show() -> None:
    """The dialog narrows with the window, and so does what one line holds."""

    assert dialog_width(360) < dialog_width(1400)
    assert dialog_line_digits(360) < dialog_line_digits(1400)


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

    # The pads really do multiply by it - all 60 decimals, since 60 fit inside the
    # engine's Decimal context.
    assert calculate("pi", scientific=True) == f"3.{PI_DECIMALS[:60]}"


def test_a_pi_longer_than_the_context_only_reaches_it_as_far_as_the_context_goes(
    view: PiView,
) -> None:
    """The limit the page has to warn about, shown rather than asserted silently.

    Adopting a 600-decimal pi stores and shows all 600 decimals, but a calculation
    runs at :data:`config.DECIMAL_PRECISION` significant digits - one of which goes
    to the ``3`` - so an answer stops at 499 decimals. A person who adopts a
    hundred thousand decimals has to be told that, or the button looks broken.
    """

    run_to_completion(view, "600")
    view.adopt_value()

    assert pi.program_pi_digits() == 600
    usable = DECIMAL_PRECISION - 1

    # What an answer actually uses - shorter than the adopted number, and still the
    # right digits as far as it goes.
    assert calculate("pi", scientific=True) == f"3.{PI_DECIMALS[:usable]}"

    # And the page says so, in the card about the program's own pi and again in the
    # status line the adoption just wrote.
    notice = find_by_key(view.build(), "pi-precision").value
    assert f"first {usable:,} of these 600 decimals" in notice
    assert f"first {usable:,} decimals" in find_by_key(view.build(), "pi-status").value


@pytest.mark.parametrize(
    ("available", "expect"),
    [
        (3, "all 3 of these decimals reach an answer"),
        (12, "all 12 of these decimals reach an answer"),
        (499, "all 499 of these decimals reach an answer"),
        (500, "uses the first 499 of these 500 decimals"),
        (1_000_000, "never multiplied"),
    ],
)
def test_the_precision_notice_says_what_the_app_can_use(
    available: int, expect: str
) -> None:
    """One sentence, and it turns on whether the context is the binding limit."""

    text = precision_notice(available)
    assert expect in text
    assert f"{DECIMAL_PRECISION} significant digits" in text


def test_the_page_shows_the_precision_it_calculates_with(view: PiView) -> None:
    """The notice is on the page before anything is computed, not only after."""

    notice = find_by_key(view.build(), "pi-precision")
    assert f"{DECIMAL_PRECISION} significant digits" in notice.value
    assert "all 12 of these decimals" in notice.value


def test_every_input_spans_the_page(view: PiView) -> None:
    """The exact-digits box was off screen while it shared a Row with the menu.

    Two inputs in one Row each take their own intrinsic width, and together they add
    up to more than the page - on a phone the second one is not reachable at all.
    Each input therefore sits in a Row of its own, where `expand` is its width.
    """

    page = view.build()
    for key in ("pi-digits", "pi-digits-exact"):
        field = find_by_key(page, key)
        assert field.expand is True, f"{key} cannot stretch across the page"
        rows = [
            control
            for control in walk(page)
            if isinstance(control, ft.Row) and field in control.controls
        ]
        assert len(rows) == 1, f"{key} is not in exactly one Row"
        assert len(rows[0].controls) == 1, f"{key} shares its Row with another input"


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


# --- what drives the progress card -------------------------------------------

def test_a_run_starts_its_own_clock_for_the_card(view: PiView) -> None:
    """The bar is repainted on the clock, not only when the engine reports or the
    reader presses something.

    A run of a hundred million digits spends a long time inside single huge
    multiplications, during which the engine reports nothing at all. A bar that waits
    for a report therefore sits still for the longest stretch of the run. So a run
    schedules a painter of its own - and it goes on the page's event loop, not through
    ``run_thread``, whose executor is shared with every other handler in the app and
    can leave the painter queued behind them: a painter that never got a worker slot is
    a bar that only moves when something else repaints the page.
    """

    set_digits(view, typed="10000")
    view.start_run()
    wait_for_run(view)

    assert view._run in view.page.threads, "the computation itself runs on a worker"
    assert view._paint_loop.__name__ in view.page.tasks, (
        "the card's painter is a task on the page's own event loop"
    )
    assert view._paint_task is not None, "the task is kept referenced while it runs"
    assert PROGRESS_PAINT_SECONDS == 0.5, "the card moves every half second"


def test_a_thousand_reports_cost_at_most_two_frames(view: PiView) -> None:
    """The worker asks for a paint with every report, and still cannot flood the page.

    The split reaches a checkpoint for every term, every product of two half results
    and every step of the tail, so a run of a hundred million digits reports millions
    of times - and it is the same thread that has to stay busy with the arithmetic. The
    cap therefore lives in :meth:`_paint_progress` rather than in either caller: the
    clock can be delayed by a multiplication and the reports arrive at their own pace,
    but the card never costs more than two frames a second.
    """

    view.build()
    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(20000, on_progress=reports.append)
    assert len(reports) > 200, "a run this size reports constantly"

    view._card_final = False
    before = view.page.updates
    for report in reports:
        view.progress = report
        view._paint_progress()
    paints = view.page.updates - before
    assert paints <= 2, f"two frames a second at most, saw {paints}"

    # The one frame that went out is not the oldest report: the next tick shows the
    # furthest the run has got, and only that.
    view._last_paint -= PROGRESS_PAINT_SECONDS
    view._paint_progress()
    assert view.progress_bar.value == pytest.approx(reports[-1].fraction)


def test_the_card_paces_itself_half_a_second_apart(view: PiView) -> None:
    """The bar moves on its own, whether or not anything is pressed.

    The clock task is driven here the way the page drives it: started next to a run and
    left alone. Over a second and a half it should push the card about three times -
    twice a second, give or take a tick - and it must not need a report arriving or a
    button being pressed to do it.
    """

    page = view.build()
    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(5000, on_progress=reports.append)
    view.progress = reports[len(reports) // 2]
    view.running = True
    view._card_final = False
    before = view.page.updates

    async def drive() -> None:
        painter = asyncio.create_task(view._paint_loop())
        # A second and a half of nothing at all: no report, no press, no interaction.
        await asyncio.sleep(1.6)
        view._card_final = True
        await painter

    asyncio.run(drive())

    paints = view.page.updates - before
    assert 2 <= paints <= 5, f"about twice a second, saw {paints}"
    assert find_by_key(page, "pi-percent").value == percent_text(
        view.progress.percent
    ), "the card is showing the furthest the run has got"


def test_one_bad_frame_does_not_kill_the_clock(view: PiView) -> None:
    """A painter task that dies quietly is a bar frozen until something is pressed.

    This is the failure mode behind "it only updates when a button is pressed": the
    clock stops asking and only a button handler repaints the page. So one frame that
    raises must cost one frame - the task outlives it, keeps asking on schedule, and
    puts the trouble where the reader can see it instead of going silent.
    """

    page = view.build()
    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(5000, on_progress=reports.append)
    view.progress = reports[len(reports) // 2]
    view.running = True
    view._card_final = False

    real_update = view.page.update
    attempts = {"raised": 0}

    def flaky_update() -> None:
        if not attempts["raised"]:
            attempts["raised"] += 1
            raise RuntimeError("patch of the card failed")
        real_update()

    # The frame fails where it really fails: sending the patch to the client.
    view.page.update = flaky_update
    before = view.page.updates

    async def drive() -> None:
        painter = asyncio.create_task(view._paint_loop())
        await asyncio.sleep(1.2)
        view._card_final = True
        await painter

    asyncio.run(drive())

    assert attempts["raised"] == 1, "the clock asks once, not until it dies"
    assert view.page.updates > before, "the frames after the bad one still go out"
    assert "patch of the card failed" in view.status_text.value
    assert find_by_key(page, "pi-percent").value == percent_text(view.progress.percent)


def test_a_tick_and_a_report_never_paint_twice_in_one_half_second(view: PiView) -> None:
    """Both painters ask, one interval decides.

    The worker paints with the report it just published and the clock paints on its
    schedule; whoever gets there first spends the interval. Without this the two
    painters would push the page twice as often as either of them alone, and a page
    update costs a patch of the whole card.
    """

    page = view.build()
    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(5000, on_progress=reports.append)

    view._card_final = False
    view.progress = reports[len(reports) // 2]
    view._paint_progress()
    painted = view.page.updates

    # A tick comes round a moment later: nothing goes out, because this half second has
    # already been spent.
    view._paint_progress()
    assert view.page.updates == painted, "the interval is shared, not doubled"

    # Half a second on, the same progress is worth showing again - the wait is not a
    # dead screen even though the engine said nothing new.
    view._last_paint -= PROGRESS_PAINT_SECONDS
    view._paint_progress()
    assert view.page.updates == painted + 1


def test_a_long_run_reports_constantly_and_pays_for_it_once(view: PiView) -> None:
    """Millions of reports must not become millions of page updates.

    The worker does ask for a paint with every report - a checkpoint inside one huge
    multiplication is often the only progress the clock could show until it wakes - so
    the cap cannot live in the caller; it lives in the painter, which is what keeps a
    checkpoint from costing more than the arithmetic between it and the next one.
    """

    page = view.build()
    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(20000, on_progress=reports.append)
    assert len(reports) > 100, "a run this size reports constantly"

    view._card_final = False
    before = view.page.updates
    for report in reports:
        view.progress = report
        view._paint_progress()
    updates = view.page.updates - before
    assert 1 <= updates <= 2, f"two paints a second at most, saw {updates}"

    # The first report went out straight away; the rest wait for the next tick, which
    # shows the furthest the run has got rather than the one that was skipped.
    assert view.progress_bar.value == pytest.approx(reports[0].fraction)
    view._last_paint -= PROGRESS_PAINT_SECONDS
    view._paint_progress()
    assert view.progress_bar.value == pytest.approx(reports[-1].fraction)
    assert find_by_key(page, "pi-percent").value == percent_text(
        reports[-1].percent
    )


def test_a_finished_run_keeps_its_own_words(view: PiView) -> None:
    """A late tick must not write a mid-run number over the outcome."""

    run_to_completion(view, "600")
    done = view.phase_text.value
    assert done == "done"

    reports: list[pi_value.PiProgress] = []
    pi_value.compute_pi(5000, on_progress=reports.append)
    view.progress = reports[len(reports) // 2]
    view._paint_progress()
    assert view.phase_text.value == done, "the card still tells the outcome"


# --- the digits dialog: one page of the number at a time ---------------------

def open_dialog_after_a_run(view: PiView, typed: str = "600") -> ft.ListView:
    """Finish a run, press "View digits", and hand back the dialog's list."""

    run_to_completion(view, typed)
    view.open_digits()
    assert len(view.page.dialogs) == 1
    dialog = view.page.dialogs[-1]
    assert dialog.modal is True
    return find_by_key(dialog, "pi-digits-list")


def digits_on_screen(lines: ft.ListView) -> str:
    """The decimals the built lines hold, concatenated."""

    return "".join(control.value for control in lines.controls)


def page_button(view: PiView, label: str) -> ft.TextButton:
    """One of the dialog's page buttons, found by the word it shows."""

    found = [
        control
        for control in walk(view.page.dialogs[-1])
        if isinstance(control, ft.TextButton) and control.content == label
    ]
    assert len(found) == 1, f"the dialog offers exactly one {label} button"
    return found[0]


def test_page_math_covers_a_number_that_outgrows_its_last_page() -> None:
    """The paging rules, without a window or a run."""

    decimals = "3" * 25_000
    assert dialog_pages(decimals) == 3
    assert dialog_page_range(decimals, 0) == (0, 10_000)
    assert dialog_page_range(decimals, 2) == (20_000, 25_000), "short, not padded"

    # A number that fits one page is still one page, and a page asked for outside the
    # number lands on an end instead of on empty space.
    assert dialog_pages("14159") == 1
    assert dialog_page_range("14159", 7) == (0, 5)
    assert dialog_page_range(decimals, 40) == (20_000, 25_000)
    assert dialog_page_range(decimals, -3) == (0, 10_000)


def test_a_long_run_is_read_a_page_at_a_time(view: PiView) -> None:
    """The list holds one page, and nothing is added under the reader's fingers.

    This is the fix for the scrollbar: a list that grows while it is being scrolled
    keeps changing the very distance the thumb is measuring, so the thumb shrank
    mid-drag and the end kept moving away. A page is fixed while it is shown, so the
    scrollbar describes the number the reader is actually in - and there is no scroll
    handler left to grow the list with.
    """

    lines = open_dialog_after_a_run(view, "25000")
    assert lines.on_scroll is None, "scrolling adds nothing to the list"
    assert lines.item_extent == DIALOG_LINE_HEIGHT, (
        "a fixed extent is what lets Flutter render only the lines in the viewport"
    )
    assert lines.build_controls_on_demand is True

    first, last = dialog_page_range(view.computation.decimals, 0)
    assert first == 0 and last == DIALOG_PAGE_DECIMALS
    assert len(lines.controls) == -(-(last - first) // LINE_DIGITS)
    assert digits_on_screen(lines) == view.computation.decimals[:DIALOG_PAGE_DECIMALS]


def test_turning_the_page_replaces_the_digits(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "25000")
    decimals = view.computation.decimals
    before = len(lines.controls)

    page_button(view, "Next").on_click()

    assert view._page == 1
    assert view.page.tasks[-1] == "_scroll_page_to_top", "a new page starts at its top"
    assert digits_on_screen(lines) == decimals[
        DIALOG_PAGE_DECIMALS : 2 * DIALOG_PAGE_DECIMALS
    ]
    # The page is swapped in, not bolted on: the list stays about a page long, which
    # is what keeps its scrollbar the same size and its end where it is.
    assert len(lines.controls) <= before + 1


def test_the_dialog_turns_to_the_end_of_the_number(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "25000")
    decimals = view.computation.decimals

    page_button(view, "Last").on_click()

    assert view._page == dialog_pages(decimals) - 1 == 2
    tail = decimals[2 * DIALOG_PAGE_DECIMALS :]
    assert len(tail) == 25_000 - 2 * DIALOG_PAGE_DECIMALS
    assert digits_on_screen(lines) == tail, "the last page is short, never padded"

    # From the last page there is nowhere to go, and the buttons say so rather than
    # sitting there waiting to do nothing.
    assert page_button(view, "Last").disabled is True
    assert page_button(view, "Next").disabled is True
    assert page_button(view, "First").disabled is False
    assert page_button(view, "Previous").disabled is False


def test_no_page_button_goes_past_either_end(view: PiView) -> None:
    """Pressed harder than anyone would press it, the dialog still stops."""

    lines = open_dialog_after_a_run(view, "25000")
    decimals = view.computation.decimals

    for _ in range(6):
        page_button(view, "First").on_click()
        page_button(view, "Previous").on_click()
    assert view._page == 0
    assert digits_on_screen(lines) == decimals[:DIALOG_PAGE_DECIMALS]

    for _ in range(9):
        page_button(view, "Next").on_click()
        page_button(view, "Last").on_click()
    assert view._page == 2
    assert digits_on_screen(lines) == decimals[2 * DIALOG_PAGE_DECIMALS :]


def test_the_footline_says_which_page_of_the_number_is_on_screen(view: PiView) -> None:
    open_dialog_after_a_run(view, "25000")
    dialog = view.page.dialogs[-1]
    assert (
        find_by_text(
            dialog,
            f"decimals 1 to {DIALOG_PAGE_DECIMALS:,} of 25,000 - page 1 of 3",
        )
        is not None
    )

    page_button(view, "Next").on_click()
    assert (
        find_by_text(
            dialog,
            f"decimals {DIALOG_PAGE_DECIMALS + 1:,} to {2 * DIALOG_PAGE_DECIMALS:,}"
            " of 25,000 - page 2 of 3",
        )
        is not None
    )


def test_a_short_run_fits_one_page_with_nowhere_to_turn(view: PiView) -> None:
    lines = open_dialog_after_a_run(view, "120")
    assert len(lines.controls) == 2, "120 decimals are two lines, never a third"
    assert digits_on_screen(lines) == PI_DECIMALS[:120]
    for label in ("First", "Previous", "Next", "Last"):
        assert page_button(view, label).disabled is True, "one page, nothing to turn"


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


def test_the_copy_button_of_the_dialog_copies_all_of_the_digits(view: PiView) -> None:
    """The whole number in one press - nobody drags over a hundred thousand digits.

    What the button hands over is the computed number, not the part of it the dialog
    happens to have built, so a run that has only been scrolled through halfway is
    still copied in full.
    """

    lines = open_dialog_after_a_run(view, "25000")
    assert (
        len(digits_on_screen(lines)) == DIALOG_PAGE_DECIMALS
    ), "only one page of it is on screen"

    dialog = view.page.dialogs[-1]
    copies = [
        control
        for control in walk(dialog)
        if isinstance(control, ft.TextButton)
        and str(control.content).startswith("Copy")
    ]
    assert len(copies) == 1, "the dialog offers exactly one way to copy"
    # And it says what it copies, so nobody has to wonder whether it is a screenful.
    assert copies[0].content == "Copy all 25,000 decimals"
    assert view.page.copies[-1]() == f"3.{view.computation.decimals}"
    assert len(view.page.copies[-1]()) == 25002, "3. plus every decimal computed"
