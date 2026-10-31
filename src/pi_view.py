"""The pi page: choose how many digits, compute them, and use them everywhere.

Computing pi is the one calculation in this app that can take longer than a
person wants to wait, so the page is built around that: a digit count anywhere
from 3 to 100 million, a progress bar weighted by the work a run actually does -
percentage, terms, which phase is under way, speed and a finish estimate under it
- a Stop button, and a "Use this value for the program" button that makes the
finished digits the pi every calculation in the app multiplies by.

The run happens on a worker thread, so the pad stays responsive, while the progress
card is repainted twice a second - by a task on the page's own event loop and by the
engine's checkpoints, spending one shared interval between them - so the bar advances as
soon as it can and the speed and estimate keep moving even while the engine is inside one
very large multiplication. The digits are shown as plain text in a scrolling dialog that
holds one page of them at a time and turns pages when asked - a hundred million digits
are never put on screen at once, which is what would make the app lag or die, and nothing
is added under the reader's fingers while they drag - and one button copies the whole
number.
"""

import asyncio
import threading
from time import monotonic
from typing import Callable, Optional

import flet as ft

import pi
import pi_value
from config import DECIMAL_PRECISION
from pi_value import PiComputation, PiProgress, format_duration
from styles import (
    ACCENT,
    CARD_BACKGROUND,
    PANEL_BACKGROUND,
    TEXT_ERROR,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_SOFT,
)

# How much of a finished run the result card shows; the rest is in the dialog.
CARD_DECIMALS = 120
CURRENT_DECIMALS = 40

# A run of a hundred million digits reports progress millions of times, and the report
# at the end of a big node can be a long time coming; the page therefore repaints the
# progress card on the clock - every half second - so the bar advances as soon as it can
# and never waits for a report one huge multiplication is holding up, nor for the reader
# to press something.
PROGRESS_PAINT_SECONDS = 0.5

# The digits dialog is the number itself in an ordinary scroll area: no line numbers,
# no monospace, no box around it. A ListView is used because it has a plain scrollbar
# and, given ``item_extent``, only ever renders the lines inside the viewport - so a
# run of a hundred million decimals can be read through without ever being on screen
# at once.
DIALOG_FONT_SIZE = 13
DIALOG_LINE_HEIGHT = 20
DIALOG_VIEWPORT_LINES = 16
DIALOG_MAX_WIDTH = 560
DIALOG_PAD = 6

# The height the dialog gives its scroll area, the room its page buttons take, and how
# many footer lines sit under those.
DIALOG_VIEWPORT_HEIGHT = DIALOG_VIEWPORT_LINES * DIALOG_LINE_HEIGHT
DIALOG_NAV_HEIGHT = 40
DIALOG_FOOTER_LINES = 1
DIALOG_MIN_LINE_DIGITS = 20

# The scrollbar is drawn inside the viewport, over whatever is at its right edge. The
# list keeps a gutter there instead, and a line is measured against what is left - so
# the thumb never sits on top of the digits it is supposed to be about.
DIALOG_SCROLLBAR_GUTTER = 14

# A digit of the dialog's font at the dialog's size, in logical pixels. How many
# decimals fit across the dialog follows from it, so a narrow window gets a shorter
# line instead of a line whose tail is cut off.
DIALOG_GLYPH_WIDTH = 8

# How many decimals the dialog holds at a time. The whole page is in the list, so the
# scrollbar covers exactly the stretch of the number the reader is in and never
# resizes under a drag, and a hundred million decimals stay out of the tree - they are
# turned a page at a time instead, which is what keeps the app from lagging or dying.
DIALOG_PAGE_DECIMALS = 10_000

# The page moves the dialog's buttons ask for. Both ends are named rather than offset
# by a huge number: that is the only way the last page of a number that does not fill
# one whole page is reachable.
_FIRST_PAGE = "first"
_LAST_PAGE = "last"
_PREV_PAGE = -1
_NEXT_PAGE = 1


def percent_text(percent: float) -> str:
    """A percentage with no pointless decimal: ``0%``, ``12.3%``, ``100%``."""

    text = f"{percent:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"


def precision_notice(available: int) -> str:
    """What the app's Decimal precision means for a pi the whole program uses.

    Every calculation in this app runs at :data:`config.DECIMAL_PRECISION`
    significant digits. A computed pi is stored and shown in full however long it
    is, but a pi longer than that context only reaches an answer as far as the
    context goes - and pi is ``3.`` something, so one significant digit is spent on
    the whole part and ``DECIMAL_PRECISION - 1`` decimals are what a calculation
    can actually multiply with. Without this said out loud, adopting a hundred
    thousand decimals looks like it did nothing to a long expression at all.
    """

    usable = DECIMAL_PRECISION - 1
    if available <= usable:
        return (
            f"Calculations run at {DECIMAL_PRECISION} significant digits, so all "
            f"{available:,} of these decimals reach an answer."
        )
    return (
        f"Calculations run at {DECIMAL_PRECISION} significant digits, so an answer "
        f"uses the first {usable:,} of these {available:,} decimals - the rest are "
        "stored and shown, but never multiplied."
    )


def dialog_width(page_width: Optional[float]) -> int:
    """How wide the digits dialog may be on this window."""

    if not page_width:  # no geometry yet - the desktop default
        return DIALOG_MAX_WIDTH
    # The dialog is centred and needs room at its sides to read as a dialog.
    return max(280, min(DIALOG_MAX_WIDTH, int(page_width) - 48))


def dialog_line_digits(page_width: Optional[float]) -> int:
    """How many decimals fit on one line of the dialog on this window.

    A line is a row of digits across the dialog's inner width, and a digit of this
    font is about :data:`DIALOG_GLYPH_WIDTH` pixels wide - so the answer follows from
    the window the dialog opens on. Rounding down is what keeps a phone from cutting
    the tail off every line of a long run, and the scrollbar's gutter is taken off
    first so the thumb cannot cover the last digits of a line.
    """

    usable = dialog_width(page_width) - 2 * DIALOG_PAD - DIALOG_SCROLLBAR_GUTTER
    return max(DIALOG_MIN_LINE_DIGITS, usable // DIALOG_GLYPH_WIDTH)


def dialog_pages(decimals: str) -> int:
    """How many pages the dialog turns through for this many decimals.

    Ceiling division: a run that does not fill its last page still gets it, and a
    number shorter than one page is still one page - the buttons only appear when
    there is actually somewhere to go.
    """

    return max(1, -(-len(decimals) // DIALOG_PAGE_DECIMALS))


def dialog_page_range(decimals: str, page: int) -> tuple[int, int]:
    """The half-open slice of the decimals one page shows: first, one past last.

    The page number is clamped into the number first, so a page before the first or
    past the last lands on an end rather than on empty space, and the last page is
    short rather than padded.
    """

    pages = dialog_pages(decimals)
    start = min(max(0, page), pages - 1) * DIALOG_PAGE_DECIMALS
    return start, min(start + DIALOG_PAGE_DECIMALS, len(decimals))


class PiView:
    """The pi calculation page.

    :param page: the page the form is shown on - used to update it and to open the
        digits dialog.
    :param make_copy_button: the app's shared copy-button factory, which can be asked
        for a button that says out loud what it copies.
    """

    def __init__(
        self,
        page: ft.Page,
        make_copy_button: Callable[..., ft.Control],
    ) -> None:
        self.page = page
        self.make_copy_button = make_copy_button

        self.computation: Optional[PiComputation] = None
        self.progress: Optional[PiProgress] = None
        self.running = False
        self.cancel = threading.Event()
        self._last_paint = 0.0
        self._card_final = False
        # The task that repaints the progress card on the clock, kept referenced so
        # the event loop is not free to drop it mid-run.
        self._paint_task: Optional[object] = None
        self._page = 0
        self._page_lines: list[ft.Text] = []
        self._page_buttons: dict[str, ft.TextButton] = {}
        self._dialog_decimals = ""
        # Rebuilt by :meth:`_open_digits_dialog` each time the digits are opened; held
        # here so they always name a real control rather than nothing.
        self._dialog_lines = ft.ListView()
        self._dialog_count = ft.Text()
        # How many decimals one dialog line holds on the window the dialog opens on;
        # set again by :meth:`_open_digits_dialog`.
        self._dialog_line_digits = dialog_line_digits(None)

        # The control tree, built by :meth:`build` and reused whenever the page is
        # opened again.
        self.root: Optional[ft.Column] = None

    # ----------------------------
    # The form
    # ----------------------------

    def build(self) -> ft.Column:
        """Assemble the page - once.

        The tree is kept and handed back unchanged. The app opens this page by
        putting the result in its content area, and the finished digits, the
        progress numbers and the typed digit count live in these very controls, so
        reopening the page after a run has to show them instead of starting again
        from an empty form.

        The handlers below read controls defined after them - they only have to
        exist by the time a handler runs.
        """

        if self.root is not None:
            self.refresh_plan(paint=False)
            self.refresh_current()
            return self.root

        self.current_text = ft.Text(size=14, selectable=True, key="pi-current")
        self.current_note = ft.Text(size=11, color=TEXT_MUTED, key="pi-current-note")
        self.view_current_button = ft.TextButton(
            "View digits",
            key="pi-view-current",
            icon=ft.Icons.VISIBILITY_OUTLINED,
            on_click=self.open_current_digits,
        )

        self.digits_dropdown = ft.Dropdown(
            key="pi-digits",
            label="Digits",
            value=str(pi.DEFAULT_PROGRAM_DIGITS),
            options=[
                ft.DropdownOption(key=str(count), text=f"{count:,} digits")
                for count in pi.PI_DIGIT_PRESETS
            ],
            on_select=self.refresh_plan,
            # `expand` inside a Row is the horizontal axis: without it a Flutter
            # dropdown sizes its box to its longest option and leaves the rest of
            # the page empty - and whatever shares the Row with it.
            expand=True,
        )
        self.digits_field = ft.TextField(
            key="pi-digits-exact",
            label="Exact number of digits",
            hint_text=f"optional - {pi.MIN_PI_DIGITS:,} to {pi.MAX_PI_DIGITS:,}",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self.refresh_plan,
            expand=True,
        )
        self.plan_text = ft.Text(size=11, color=TEXT_FAINT, key="pi-plan")
        # The notice about how much of a pi the app's own precision can use. It
        # belongs with the pi the program uses, not with the digit field: the limit
        # is the engine's Decimal context, not anything the run can be talked into.
        self.precision_text = ft.Text(
            precision_notice(pi.DEFAULT_PROGRAM_DIGITS),
            size=11,
            color=TEXT_FAINT,
            key="pi-precision",
        )

        self.compute_button = ft.FilledButton(
            "Compute pi",
            key="pi-compute",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.start_run,
        )
        self.stop_button = ft.OutlinedButton(
            "Stop", key="pi-stop", disabled=True, on_click=self.stop_run
        )

        self.progress_bar = ft.ProgressBar(
            key="pi-progress",
            value=0.0,
            color=ACCENT,
            # The bar sits on a card of CARD_BACKGROUND; giving the track the same
            # colour made the unfilled part invisible, so a run looked like a
            # growing blob rather than a share of a known whole.
            bgcolor=PANEL_BACKGROUND,
            bar_height=10,
            border_radius=5,
        )
        self.percent_text = ft.Text(
            "0%", size=13, weight=ft.FontWeight.BOLD, key="pi-percent"
        )
        self.terms_text = ft.Text("", size=11, color=TEXT_MUTED, key="pi-terms")
        # Which of the run's phases is taking the time. The bar alone cannot say it,
        # and a bar that seems to have stopped is what makes a wait feel broken -
        # the last square root and division are a third of a long run on their own.
        self.phase_text = ft.Text("", size=11, color=TEXT_MUTED, key="pi-phase")
        self.speed_text = ft.Text("speed -", size=11, color=TEXT_MUTED, key="pi-speed")
        self.estimate_text = ft.Text(
            "estimate -", size=11, color=TEXT_MUTED, key="pi-estimate"
        )

        self.result_text = ft.Text(
            "", key="pi-result", selectable=True, font_family="monospace", size=13
        )
        self.status_text = ft.Text("", size=11, color=TEXT_SOFT, key="pi-status")
        self.view_button = ft.TextButton(
            "View digits",
            key="pi-view-digits",
            icon=ft.Icons.VISIBILITY,
            disabled=True,
            on_click=self.open_digits,
        )
        self.adopt_button = ft.FilledButton(
            "Use this value for the program",
            key="pi-adopt",
            icon=ft.Icons.CHECK,
            disabled=True,
            on_click=self.adopt_value,
        )

        self.refresh_plan(paint=False)
        self.refresh_current()

        self.root = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SUPPORT, size=28, color=ACCENT),
                        ft.Text("Pi Calculation", size=22, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=12,
                ),
                ft.Text(
                    "Compute pi with the Chudnovsky series, watch the run, and make "
                    "the result the pi every calculation in the app uses.",
                    color=TEXT_MUTED,
                ),
                self._card(
                    ft.Text("PI THE PROGRAM USES NOW", size=10, color=TEXT_MUTED),
                    self.current_text,
                    self.current_note,
                    self.precision_text,
                    self.view_current_button,
                ),
                # One input per Row. Side by side, the dropdown and the field take
                # their own intrinsic widths and add up to more than the page, which
                # is what pushed the exact-digits box off screen - on a phone it was
                # off screen entirely.
                self._stretched(self.digits_dropdown),
                self._stretched(self.digits_field),
                self.plan_text,
                ft.Row([self.compute_button, self.stop_button], spacing=10),
                self._card(
                    self.progress_bar,
                    ft.Row(
                        [self.percent_text, self.terms_text],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.phase_text,
                    self.speed_text,
                    self.estimate_text,
                ),
                self._card(
                    ft.Text("RESULT", size=10, color=TEXT_MUTED),
                    self.result_text,
                    self.status_text,
                    ft.Row(
                        [
                            self.view_button,
                            self.adopt_button,
                            self.make_copy_button(
                                lambda: self.computation.text()
                                if self.computation
                                else "",
                                tooltip="Copy computed pi",
                            ),
                        ],
                        spacing=10,
                    ),
                ),
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        return self.root

    def _card(self, *lines: ft.Control) -> ft.Container:
        return ft.Container(
            content=ft.Column(list(lines), spacing=6),
            bgcolor=CARD_BACKGROUND,
            border_radius=8,
            padding=10,
        )

    def _stretched(self, field: ft.Control) -> ft.Row:
        """Put one input in a Row of its own, where it can span the page.

        A Field inside a Column would be stretched vertically instead of
        horizontally, so each input gets a Row that already spans the page and
        `expand` on the field becomes its width. This is the same arrangement the
        unit conversion form uses for its dropdowns, and it is why both forms keep
        their proportions at any window width - and on a phone.
        """

        return ft.Row([field])

    # ----------------------------
    # Choosing how many digits
    # ----------------------------

    def requested_digits(self) -> Optional[int]:
        """The digit count the form asks for, or None if it does not read as one.

        A number typed into the exact field wins over the menu, so a count between
        the presets - 500 000, say - is reachable from the page without a preset for
        it. The menu holds only what fits the app's own ceiling.
        """

        typed = (self.digits_field.value or "").strip()
        typed = typed.replace(",", "").replace("_", "")
        if typed:
            try:
                return int(typed)
            except ValueError:
                return None
        try:
            return int(self.digits_dropdown.value)
        except (TypeError, ValueError):
            return None

    def digits_are_valid(self, digits: Optional[int]) -> bool:
        return digits is not None and pi.MIN_PI_DIGITS <= digits <= pi.MAX_PI_DIGITS

    def refresh_plan(self, e=None, paint: bool = True) -> None:
        """Show what the current choice would mean before anything is computed.

        ``paint`` is off while :meth:`build` is still assembling the tree - the
        controls are not on the page yet, so there is nothing to repaint.
        """

        del e
        digits = self.requested_digits()
        if not self.digits_are_valid(digits):
            self.plan_text.value = (
                f"Pick a whole number of decimals between {pi.MIN_PI_DIGITS} and "
                f"{pi.MAX_PI_DIGITS:,}."
            )
            self.plan_text.color = TEXT_ERROR
            if not self.running:
                self.compute_button.disabled = True
        else:
            terms = pi.pi_term_count(digits)
            self.plan_text.value = (
                f"{digits:,} decimals - about {terms:,} terms of the Chudnovsky series"
            )
            self.plan_text.color = TEXT_FAINT
            if not self.running:
                self.compute_button.disabled = False
        if paint:
            self.page.update()

    # ----------------------------
    # The run
    # ----------------------------

    def start_run(self, e=None) -> None:
        """Start a run on a worker thread and let the page keep responding."""

        del e
        digits = self.requested_digits()
        if not self.digits_are_valid(digits):
            self.refresh_plan()
            return

        self.running = True
        self.cancel.clear()
        self.computation = None
        self.progress = None
        self._last_paint = 0.0
        self._card_final = False

        self.compute_button.disabled = True
        self.stop_button.disabled = False
        self.view_button.disabled = True
        self.adopt_button.disabled = True

        self.progress_bar.value = 0.0
        self.percent_text.value = "0%"
        self.terms_text.value = f"0 / {pi.pi_term_count(digits):,} terms"
        self.phase_text.value = "starting the binary split ..."
        self.speed_text.value = "speed -"
        self.estimate_text.value = "estimate -"
        self.result_text.value = ""
        self.status_text.value = f"computing {digits:,} decimals ..."
        self.page.update()

        # Flet's own background-thread API rather than a bare threading.Thread: the
        # worker gets this page bound to its context, and on a web build - where
        # Python threads are not available - it runs inline instead of dying.
        self.page.run_thread(self._run, digits)
        # The card has to move whether or not the engine is reporting: one very large
        # multiplication can hold a report back for a long stretch, and a bar that waits
        # for it looks stuck for the longest part of the run. The painter goes through
        # the page's own event loop rather than a second run_thread, because run_thread
        # queues on an executor shared with every other handler in the app - a painter
        # left waiting for a worker slot is a bar that only moves when something else
        # repaints the page. The reference is kept: a task nothing points at can be
        # garbage collected out from under the run.
        self._paint_task = self.page.run_task(self._paint_loop)

    async def _paint_loop(self) -> None:
        """Repaint the progress card every half second while a run is going.

        A task on the page's own event loop rather than a thread: it only reads the
        progress the worker last published, and :meth:`_paint_progress` refuses to
        touch the page once the run is over, so an idle tick costs nothing and the card
        keeps moving whether or not the reader touches anything.

        The half second is anchored to a schedule rather than counted out in sleeps. A
        loop sharing the interpreter with a computation grinding through huge integers
        wakes late by tens of milliseconds at a time, and sleeps measured one after
        another add that lateness up - the card would drift to a paint every two thirds
        of a second and worse. Anchoring each wait to the next due time keeps the paints
        on the half second however late individual wakes are.

        One frame that cannot be sent costs one frame and nothing more: the task
        outlives it and puts the trouble on the card. A painter that dies quietly is a
        bar that only moves when some other handler repaints the page, which is what
        made this card look frozen until something was pressed.
        """

        loop = asyncio.get_running_loop()
        due = loop.time() + PROGRESS_PAINT_SECONDS
        while self.running and not self._card_final:
            delay = due - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                self._paint_progress()
            except Exception as error:
                # The next tick shows this wording; a fault that clears with the next
                # report is gone from the card by then as well.
                self.status_text.value = f"progress display failed: {error}"
            # A wake that came late is made up on the schedule rather than pushing the
            # whole interval back; one that came very late is not answered with a burst
            # of repaints, since the next paint is due half a second from this one.
            due = max(due, loop.time()) + PROGRESS_PAINT_SECONDS

    def stop_run(self, e=None) -> None:
        """Ask a running computation to stop at its next checkpoint."""

        del e
        if not self.running:
            return
        self.cancel.set()
        self.stop_button.disabled = True
        # The request is honoured at any node of the split - a term, a product of
        # two halves, or a step of the tail - so the wording cannot promise a term.
        self.status_text.value = "stopping at the next checkpoint ..."
        self.page.update()

    def _run(self, digits: int) -> None:
        """The worker thread body: compute, then hand the outcome to the page.

        Progress is reported from inside the binary split - millions of times for a
        hundred million digits. Each report is published and asks for a paint, because a
        checkpoint is often the only progress that can be shown while the interpreter is
        busy with one huge multiplication; :meth:`_paint_loop` asks on the clock as well.
        Both are capped together inside :meth:`_paint_progress`, so the checkpoints cannot
        cost the run more than two page updates a second.
        """

        def on_progress(progress: PiProgress) -> None:
            self.progress = progress
            self._paint_progress()

        try:
            computation = pi_value.compute_pi(
                digits, on_progress=on_progress, cancel_check=self.cancel.is_set
            )
        except Exception as error:  # a failed run must not leave the page waiting
            self.running = False
            self._card_final = True
            self.computation = None
            self.status_text.value = f"could not compute pi: {error}"
            self._finish_run_controls()
            self.page.update()
            return

        self.running = False
        # From here the card tells the outcome rather than the run, so the clock's
        # painter is stood down: a late tick must not write a mid-run number over
        # these lines.
        self._card_final = True
        self.computation = computation
        if computation.cancelled:
            stopped = self.progress
            if stopped:
                where = (
                    f"{stopped.terms_done:,} of {stopped.terms_total:,} terms - "
                    f"{percent_text(stopped.percent)} of the run, during "
                    f"{stopped.phase_label}"
                )
            else:
                where = "before its first term"
            self.phase_text.value = "stopped"
            self.status_text.value = (
                f"stopped after {where} - nothing was computed, and the program "
                "still uses its previous pi"
            )
        else:
            self.progress_bar.value = 1.0
            self.percent_text.value = "100%"
            self.terms_text.value = (
                f"{pi.pi_term_count(digits):,} / {pi.pi_term_count(digits):,} terms"
            )
            self.phase_text.value = "done"
            self.speed_text.value = (
                f"speed {computation.digits / computation.seconds:,.0f} digits/s"
            )
            self.estimate_text.value = f"took {format_duration(computation.seconds)}"
            self.result_text.value = computation.format(CARD_DECIMALS)
            self.status_text.value = (
                f"{digits:,} decimals in {format_duration(computation.seconds)} - "
                "press the button below to make the whole program calculate with it"
            )
        self._finish_run_controls()
        self.page.update()

    def _finish_run_controls(self) -> None:
        """Re-arm the buttons once a run is over, however it ended."""

        self.compute_button.disabled = False
        self.stop_button.disabled = True
        self.view_button.disabled = self.computation is None or bool(
            self.computation.cancelled
        )
        self.adopt_button.disabled = not (
            self.computation and self.computation.complete
        )

    def _paint_progress(self) -> None:
        """Push the running numbers into the progress card, at most twice a second.

        Two things ask for a paint: the clock (:meth:`_paint_loop`) and the worker,
        every time the split reaches a checkpoint. Either of them can be the one that
        gets there first, and a long run reports millions of times, so the cap lives
        here rather than in either caller - a hundred million reports cannot become a
        hundred million page updates, and the card never goes longer than half a
        second without fresh numbers.

        Once a run has ended the card belongs to the outcome - :meth:`_run` says so with
        ``_card_final`` - and a late tick must not write a mid-run number over what a
        finished run reports.
        """

        progress = self.progress
        if progress is None or self._card_final:
            return
        now = monotonic()
        if now - self._last_paint < PROGRESS_PAINT_SECONDS:
            return
        self._last_paint = now
        self.progress_bar.value = progress.fraction
        self.percent_text.value = percent_text(progress.percent)
        self.terms_text.value = (
            f"{progress.terms_done:,} / {progress.terms_total:,} terms"
        )
        # The bar divides measured cost, not terms, so it keeps moving after the
        # last term - and this line is what says what the wait is busy with then.
        self.phase_text.value = f"now: {progress.phase_label}"
        self.speed_text.value = f"speed {progress.digits_per_second:,.0f} digits/s"
        left = format_duration(progress.seconds_left)
        total = format_duration(progress.estimated_seconds)
        self.estimate_text.value = f"about {left} left - {total} in total"
        self.page.update()

    # ----------------------------
    # Adopting the result
    # ----------------------------

    def adopt_value(self, e=None) -> None:
        """The "Use this value for the program" button: the run becomes the app's pi."""

        del e
        if not self.computation or not self.computation.complete:
            return
        try:
            pi_value.adopt(self.computation)
        except ValueError as error:
            self.status_text.value = f"that value cannot be used: {error}"
            self.page.update()
            return

        self.refresh_current()
        digits = pi.program_pi_digits()
        usable = DECIMAL_PRECISION - 1
        reached = (
            "every decimal of it reaches an answer"
            if digits <= usable
            else f"an answer uses its first {usable:,} decimals"
        )
        self.status_text.value = (
            f"the program now calculates with pi to {digits:,} decimals - "
            f"{reached} at the app's {DECIMAL_PRECISION}-digit precision"
        )
        self.page.update()

    def refresh_current(self) -> None:
        """Show the pi the program is calculating with right now."""

        digits = pi.program_pi_digits()
        self.current_text.value = pi.format_pi_digits(
            pi.program_pi_text(), digits, CURRENT_DECIMALS
        )
        self.current_note.value = f"{digits:,} decimals, computed by this app"
        # Repeated after every adoption, because this is the point where a person
        # might expect a million decimals to change a million digits of an answer.
        self.precision_text.value = precision_notice(digits)
        self.view_current_button.disabled = digits < 1

    # ----------------------------
    # The digits dialog
    # ----------------------------

    def open_digits(self, e=None) -> None:
        """Show the digits of the run that just finished."""

        del e
        if not self.computation or not self.computation.complete:
            return
        self._open_digits_dialog(
            self.computation.decimals,
            f"Pi to {self.computation.digits:,} decimals",
        )

    def open_current_digits(self, e=None) -> None:
        """Show the digits of the pi the program currently calculates with."""

        del e
        self._open_digits_dialog(
            pi.program_pi_decimals(),
            f"Pi the program uses - {pi.program_pi_digits():,} decimals",
        )

    def _open_digits_dialog(self, decimals: str, heading: str) -> None:
        """Open the digits in an ordinary scroll area, one page of them at a time.

        A finished run can be a hundred million digits long, and putting that many
        text controls on the screen at once is exactly what would make the app lag
        or die. The dialog therefore keeps a single page of
        :data:`DIALOG_PAGE_DECIMALS` decimals in the list and turns pages when asked.
        ``item_extent`` still means the Flutter side only renders the lines inside the
        viewport, and - unlike a list that grows while it is being scrolled - the page
        never changes under the reader's fingers, so the scrollbar covers the stretch
        of the number actually on show: its thumb stays the same size mid-drag, it
        always reaches the real end of the page, and it cannot run off past the
        bottom.

        The lines hold the digits and nothing else - no line numbers, no monospace,
        no box. It is a number being read, not source code.
        """

        self._dialog_decimals = decimals
        self._page = 0
        # The line length and the dialog's width follow the window the dialog opens
        # on: at a fixed length a phone cut the tail off every line, which made a
        # long run unreadable there.
        window_width = getattr(self.page, "width", None)
        self._dialog_line_digits = dialog_line_digits(window_width)

        self._page_buttons = {
            move: self._page_button(move, label)
            for move, label in (
                (_FIRST_PAGE, "First"),
                (_PREV_PAGE, "Previous"),
                (_NEXT_PAGE, "Next"),
                (_LAST_PAGE, "Last"),
            )
        }
        self._dialog_lines = ft.ListView(
            controls=[],
            item_extent=DIALOG_LINE_HEIGHT,
            build_controls_on_demand=True,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            # The thumb is drawn inside the viewport, over whatever sits at its right
            # edge, so the list keeps that edge clear instead of letting the thumb sit
            # on top of the digits it is meant to be about.
            padding=ft.Padding(0, 0, DIALOG_SCROLLBAR_GUTTER, 0),
            key="pi-digits-list",
        )
        self._dialog_count = ft.Text(size=11, color=TEXT_FAINT, selectable=True)
        self._show_page(paint=False)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(heading, size=18),
                content=ft.Column(
                    [
                        self._dialog_lines,
                        ft.Row(
                            list(self._page_buttons.values()), spacing=4, wrap=True
                        ),
                        self._dialog_count,
                    ],
                    spacing=8,
                    height=DIALOG_VIEWPORT_HEIGHT
                    + DIALOG_NAV_HEIGHT
                    + DIALOG_FOOTER_LINES * DIALOG_LINE_HEIGHT,
                    width=dialog_width(window_width),
                ),
                actions=[
                    self.make_copy_button(
                        lambda: f"3.{decimals}",
                        tooltip="Copy every decimal of this pi",
                        label=f"Copy all {len(decimals):,} decimals",
                    ),
                    ft.TextButton(
                        content="Close", on_click=lambda: self.page.pop_dialog()
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )
        self.page.update()

    def _page_button(self, move: str | int, label: str) -> ft.TextButton:
        """One of the four page buttons, bound to the move it asks for.

        ``e`` is optional: the page hands the click event to it, while a test presses
        the button by calling the handler bare.
        """

        return ft.TextButton(
            content=label, on_click=lambda e=None, step=move: self._turn_page(step)
        )

    def _dialog_line(self, start: int, end: int) -> ft.Text:
        """One line of the dialog: the digits, and nothing else on them.

        ``start`` is where the line begins in the whole number, which is how a page
        after the first starts mid-number rather than at its beginning, and ``end`` is
        where the page stops - so a line never carries digits that belong to the next
        page.
        """

        width = self._dialog_line_digits
        return ft.Text(
            self._dialog_decimals[start : min(start + width, end)],
            size=DIALOG_FONT_SIZE,
            no_wrap=True,
            selectable=True,
        )

    def _dialog_footline(self) -> str:
        """Where the page on screen sits inside the whole number."""

        total = len(self._dialog_decimals)
        pages = dialog_pages(self._dialog_decimals)
        if pages == 1:
            return f"all {total:,} decimals on screen"
        first, last = dialog_page_range(self._dialog_decimals, self._page)
        return (
            f"decimals {first + 1:,} to {last:,} of {total:,} - "
            f"page {self._page + 1:,} of {pages:,}"
        )

    def _show_page(self, paint: bool = True) -> None:
        """Put the page the reader is on into the list, and say where they are.

        The whole page goes in at once, so the list keeps a fixed extent for as long
        as that page is shown - which is what makes the scrollbar honest - and turning
        a page replaces the controls instead of appending to them. The scroll returns
        to the top with it, or the reader would land halfway down digits they have not
        seen yet.
        """

        first, last = dialog_page_range(self._dialog_decimals, self._page)
        width = self._dialog_line_digits
        self._page_lines = [
            self._dialog_line(start, last) for start in range(first, last, width)
        ]
        self._dialog_lines.controls = self._page_lines
        for move, button in self._page_buttons.items():
            button.disabled = not self._can_turn_page(move)
        self._dialog_count.value = self._dialog_footline()
        if not paint:
            return
        # A page turn starts at the top of the new page: the scroll position outlives
        # the controls it was measuring, so without this the reader would land halfway
        # down digits they have not seen. It is a coroutine, so it goes through the
        # page's own task runner.
        self.page.run_task(self._scroll_page_to_top)
        self.page.update()

    async def _scroll_page_to_top(self) -> None:
        """Jump the digits back to the top of the scroll area."""

        await self._dialog_lines.scroll_to(offset=0, duration=0)

    def _can_turn_page(self, move: str | int) -> bool:
        """Whether a page button has anywhere to go from the page on screen.

        A number that fits in one page has nowhere to turn, so all four buttons are
        disabled instead of sitting there as dead weight.
        """

        pages = dialog_pages(self._dialog_decimals)
        if pages <= 1:
            return False
        if move == _FIRST_PAGE:
            return self._page > 0
        if move == _LAST_PAGE:
            return self._page < pages - 1
        return 0 <= self._page + int(move) < pages

    def _turn_page(self, move: str | int) -> None:
        """Turn to another page of the digits - and never past either end.

        Both ends are asked for by name rather than by a huge offset, so the last page
        of a number that does not fill one whole page is reachable too.
        """

        pages = dialog_pages(self._dialog_decimals)
        if move == _FIRST_PAGE:
            page = 0
        elif move == _LAST_PAGE:
            page = pages - 1
        else:
            page = self._page + int(move)
        self._page = min(max(page, 0), pages - 1)
        self._show_page()

