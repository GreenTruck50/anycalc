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
opens holding one batch of them and builds the next batch as the reader scrolls near the
bottom - a hundred million digits are never put on screen at once, which is what would
make the app lag or die - and one button copies the whole number.

Under the result, a search box answers the other question a person asks about a long
number: "where does this digit string appear?". It takes digits only, and it searches
whatever the page actually holds - the decimals of the run that last finished, or the
pi the program calculates with while no run is on the page.
"""

import asyncio
import re
import threading
from time import monotonic
from typing import Awaitable, Callable, Generic, Optional, Protocol, TypeVar

import flet as ft

import pi
import pi_value
from config import DECIMAL_PRECISION
from dropdowns import searchable
from pi_value import PiComputation, PiProgress, format_duration
import styles

# How much of a finished run the result card shows; the rest is in the dialog.
CARD_DECIMALS = 120
CURRENT_DECIMALS = 40

# A run of a hundred million digits reports progress millions of times, and the report
# at the end of a big node can be a long time coming; the page therefore repaints the
# progress card on the clock - every half second - so the bar advances as soon as it can
# and never waits for a report one huge multiplication is holding up, nor for the reader
# to press something.
PROGRESS_PAINT_SECONDS = 0.5

# The digits dialog is one large, wrapping label inside a plain scroll area.
DIALOG_FONT_SIZE = 18
DIALOG_MAX_WIDTH = 560
DIALOG_VIEWPORT_HEIGHT = 340

# How many decimals the dialog appends to its label at a time.
DIALOG_BATCH_DECIMALS = 10_000

# Load more shortly before the label reaches the end of the scroll area.
DIALOG_LOAD_AHEAD_PIXELS = 160

# Keep long runs from making the dialog's label unbounded. The copy button still
# provides the entire value.
DIALOG_MAX_LOADED_DECIMALS = 200_000


class _PiPage(Protocol):
    @property
    def width(self) -> int | float | None: ...

    def update(self, *_controls: ft.Control) -> None: ...

    def show_dialog(self, dialog: ft.AlertDialog) -> None: ...

    def pop_dialog(self) -> ft.DialogControl | None: ...

    def run_thread(self, handler: Callable[..., object], *args: object) -> object: ...

    def run_task(self, handler: Callable[..., Awaitable[object]]) -> object: ...


PageT = TypeVar("PageT", bound=_PiPage)


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


def dialog_load_ceiling(total: int) -> int:
    """How many decimals the dialog may hold at once for a number this long.

    The ceiling only ever bites on numbers longer than it; a shorter number is simply
    all loadable. One batch is taken as a floor, so a mis-tuned ceiling can never leave
    the dialog unable to open with the digits it opens on.
    """

    return min(total, max(DIALOG_MAX_LOADED_DECIMALS, DIALOG_BATCH_DECIMALS))


def dialog_batch_range(decimals: str, loaded: int) -> tuple[int, int]:
    """The half-open slice of the decimals to build next: first, one past last.

    ``loaded`` is how far the dialog has already built, so the next batch starts where
    the last one ended. The slice is clamped at both ends - never before the start of
    the number, never past its end, never past the ceiling - which is what makes the
    last batch short instead of padded and makes asking for more once the whole number
    is on screen ask for nothing.
    """

    start = min(max(loaded, 0), len(decimals))
    return start, min(start + DIALOG_BATCH_DECIMALS, dialog_load_ceiling(len(decimals)))


# The longest digit string a search will take. Anything longer is not a question
# about a number, it is the number itself being pasted back at the page.
MAX_SEARCH_PATTERN_DIGITS = 100

# What the search field throws away: everything that is not a decimal digit. The
# field also carries this as its input filter, and the page re-applies it before a
# search runs - see PiView.search_pattern.
NON_DIGITS = re.compile(r"[^0-9]")
NON_DIGITS_PATTERN = r"[^0-9]"


def search_decimals(decimals: str, pattern: str) -> tuple[int, int]:
    """Where a digit string first appears in a run of decimals, and how often.

    Returns ``(start, count)`` where ``start`` is the 1-based position of the first
    occurrence counted in decimals after the point - the same reckoning as the digit
    counts and the digits dialog, where ``3.1415`` has its ``1`` at decimal 1. Returns
    ``(-1, 0)`` when the string is absent, and an empty pattern never matches: asking
    where "" appears in a number is not a question a person wants an answer to.
    """

    if not pattern:
        return -1, 0
    first = decimals.find(pattern)
    if first < 0:
        return -1, 0
    return first + 1, decimals.count(pattern)


def search_scope_text(decimals: str, source: str) -> str:
    """Which digits a search runs over, so the page can say it out loud."""

    return f"searches the {len(decimals):,} decimals of {source}"


def search_result_text(pattern: str, decimals: str, source: str) -> str:
    """What searching ``decimals`` for ``pattern`` has to report.

    A position is only meaningful next to the number it was found in, so every
    sentence names both: how long the number is, whose digits they are, and where in
    them the string sits.
    """

    total = len(decimals)
    if not pattern:
        return "Type the digits to look for."
    if len(pattern) > MAX_SEARCH_PATTERN_DIGITS:
        return (
            f"{pattern} is {len(pattern):,} digits long - a search string is "
            f"limited to {MAX_SEARCH_PATTERN_DIGITS:,} digits."
        )
    if len(pattern) > total:
        return (
            f"{pattern} is {len(pattern)} digits long - longer than the "
            f"{total:,} decimals of {source}, so it cannot appear in them."
        )

    start, count = search_decimals(decimals, pattern)
    if start < 0:
        return (
            f"{pattern} is not in the {total:,} decimals of {source} - compute more "
            "decimals and search again."
        )

    last = start + len(pattern) - 1
    where = (
        f"decimal {start:,}"
        if len(pattern) == 1
        else f"decimals {start:,} to {last:,}"
    )
    if count == 1:
        return (
            f"{pattern} appears once in the {total:,} decimals of {source}, at "
            f"{where} after the decimal point."
        )
    return (
        f"{pattern} appears {count:,} times in the {total:,} decimals of {source}, "
        f"first at {where} after the decimal point."
    )


class PiView(Generic[PageT]):
    """The pi calculation page.

    :param page: the page the form is shown on - used to update it and to open the
        digits dialog.
    :param make_copy_button: the app's shared copy-button factory, which can be asked
        for a button that says out loud what it copies.
    :param on_program_pi_changed: callback for persisting an adopted program pi.
    """

    def __init__(
        self,
        page: PageT,
        make_copy_button: Callable[..., ft.Control],
        on_program_pi_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.page = page
        self.make_copy_button = make_copy_button
        self.on_program_pi_changed = on_program_pi_changed

        self.computation: Optional[PiComputation] = None
        self.progress: Optional[PiProgress] = None
        self.running = False
        self.cancel = threading.Event()
        self._last_paint = 0.0
        self._card_final = False
        # The task that repaints the progress card on the clock, kept referenced so
        # the event loop is not free to drop it mid-run.
        self._paint_task: Optional[object] = None
        # The digits dialog: the number it is showing, how many decimals of it the
        # label currently holds, and the guard that keeps a burst of notifications
        # from racing over the same batch. Rebuilt by
        # :meth:`_open_digits_dialog` each time the digits are opened; held here so
        # they always name a real control rather than nothing.
        self._dialog_decimals = ""
        self._dialog_loaded = 0
        self._dialog_loading = False
        self._dialog_label = ft.Text()
        self._dialog_scrollbox = ft.ListView()
        self._dialog_count = ft.Text()

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
            self.refresh_search_state(paint=False)
            return self.root

        self.current_text = ft.Text(size=14, selectable=True, key="pi-current")
        self.current_note = ft.Text(size=11, color=styles.TEXT_MUTED, key="pi-current-note")
        self.view_current_button = ft.TextButton(
            "View digits",
            key="pi-view-current",
            icon=ft.Icons.VISIBILITY_OUTLINED,
            on_click=self.open_current_digits,
        )

        self.digits_dropdown = searchable(
            ft.Dropdown(
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
            ),
            self.page,
        )
        self.digits_field = ft.TextField(
            key="pi-digits-exact",
            label="Exact number of digits",
            hint_text=f"optional - {pi.MIN_PI_DIGITS:,} to {pi.MAX_PI_DIGITS:,}",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self.refresh_plan,
            expand=True,
        )
        self.plan_text = ft.Text(size=11, color=styles.TEXT_FAINT, key="pi-plan")
        # The notice about how much of a pi the app's own precision can use. It
        # belongs with the pi the program uses, not with the digit field: the limit
        # is the engine's Decimal context, not anything the run can be talked into.
        self.precision_text = ft.Text(
            precision_notice(pi.DEFAULT_PROGRAM_DIGITS),
            size=11,
            color=styles.TEXT_FAINT,
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
            color=styles.ACCENT,
            # The bar sits on a card of CARD_BACKGROUND; giving the track the same
            # colour made the unfilled part invisible, so a run looked like a
            # growing blob rather than a share of a known whole.
            bgcolor=styles.PANEL_BACKGROUND,
            bar_height=10,
            border_radius=5,
        )
        self.percent_text = ft.Text(
            "0%", size=13, weight=ft.FontWeight.BOLD, key="pi-percent"
        )
        self.terms_text = ft.Text("", size=11, color=styles.TEXT_MUTED, key="pi-terms")
        # Which of the run's phases is taking the time. The bar alone cannot say it,
        # and a bar that seems to have stopped is what makes a wait feel broken -
        # the last square root and division are a third of a long run on their own.
        self.phase_text = ft.Text("", size=11, color=styles.TEXT_MUTED, key="pi-phase")
        self.speed_text = ft.Text("speed -", size=11, color=styles.TEXT_MUTED, key="pi-speed")
        self.estimate_text = ft.Text(
            "estimate -", size=11, color=styles.TEXT_MUTED, key="pi-estimate"
        )

        self.result_text = ft.Text(
            "", key="pi-result", selectable=True, font_family="monospace", size=13
        )
        self.status_text = ft.Text("", size=11, color=styles.TEXT_SOFT, key="pi-status")
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
            visible=False,
            on_click=self.adopt_value,
        )

        # The digit search. It takes digits and nothing else: the field asks for a
        # numeric keyboard, carries a filter that drops every non-digit as it is
        # typed or pasted, and the page drops them again before searching - a
        # desktop keyboard sends keystrokes that a soft-keyboard hint cannot refuse.
        self.search_field = ft.TextField(
            key="pi-search",
            label="Find digits",
            hint_text="digits only - e.g. 141592",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(
                regex_string=NON_DIGITS_PATTERN, allow=False
            ),
            on_change=self.refresh_search_state,
            on_submit=self.run_search,
        )
        self.search_button = ft.OutlinedButton(
            "Search digits",
            key="pi-search-go",
            icon=ft.Icons.SEARCH,
            icon_color=styles.ACCENT,
            disabled=True,
            on_click=self.run_search,
        )
        # Which digits the search runs over, because the page holds two sets: the
        # last finished run, and the pi the program calculates with.
        self.search_scope = ft.Text(
            "", size=11, color=styles.TEXT_FAINT, key="pi-search-scope"
        )
        self.search_result = ft.Text(
            "",
            key="pi-search-result",
            size=12,
            color=styles.TEXT_SOFT,
            selectable=True,
        )

        self.refresh_plan(paint=False)
        self.refresh_current()
        self.refresh_search_state(paint=False)

        self.root = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SUPPORT, size=28, color=styles.ACCENT),
                        ft.Text("Pi Calculation", size=22, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=12,
                ),
                ft.Text(
                    "Compute pi with the Chudnovsky series, watch the run, and make "
                    "the result the pi every calculation in the app uses.",
                    color=styles.TEXT_MUTED,
                ),
                self._card(
                    ft.Text("PI THE PROGRAM USES NOW", size=10, color=styles.TEXT_MUTED),
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
                    ft.Text("RESULT", size=10, color=styles.TEXT_MUTED),
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
                self._card(
                    ft.Text("DIGIT SEARCH", size=10, color=styles.TEXT_MUTED),
                    self._stretched(self.search_field),
                    ft.Row([self.search_button], spacing=10),
                    self.search_scope,
                    self.search_result,
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
            bgcolor=styles.CARD_BACKGROUND,
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
            dropdown_value = self.digits_dropdown.value
            if dropdown_value is None:
                return None
            return int(dropdown_value)
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
        if digits is None or not self.digits_are_valid(digits):
            self.plan_text.value = (
                f"Pick a whole number of decimals between {pi.MIN_PI_DIGITS} and "
                f"{pi.MAX_PI_DIGITS:,}."
            )
            self.plan_text.color = styles.TEXT_ERROR
            if not self.running:
                self.compute_button.disabled = True
        else:
            terms = pi.pi_term_count(digits)
            self.plan_text.value = (
                f"{digits:,} decimals - about {terms:,} terms of the Chudnovsky series"
            )
            self.plan_text.color = styles.TEXT_FAINT
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
        if digits is None or not self.digits_are_valid(digits):
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
        self.adopt_button.visible = False

        self.progress_bar.value = 0.0
        self.percent_text.value = "0%"
        self.terms_text.value = f"0 / {pi.pi_term_count(digits):,} terms"
        self.phase_text.value = "starting the binary split ..."
        self.speed_text.value = "speed -"
        self.estimate_text.value = "estimate -"
        self.result_text.value = ""
        self.status_text.value = f"computing {digits:,} decimals ..."
        # A run in flight has no answer to search yet, so the search card goes back
        # to the pi the program uses and drops the answer it printed for the last run.
        self.search_result.value = ""
        self.refresh_search_state(paint=False)
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
        self.adopt_button.visible = not self.adopt_button.disabled
        # A run that finished is now the longest number the page holds, so it is what
        # a digit search runs over; a run that stopped holds nothing, and the search
        # goes back to the program's pi. Either way the search card has to say which.
        self.refresh_search_state(paint=False)

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

        self.adopt_button.visible = False
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
        if self.on_program_pi_changed is not None:
            self.on_program_pi_changed()

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
    # Finding digits in the number
    # ----------------------------

    def search_target(self) -> tuple[str, str]:
        """The decimals a search runs over, and what to call them out loud.

        The page holds two numbers: the run that last finished, and the pi the
        program calculates with. A search uses the run when there is one - it is the
        longer number, and the one the reader is looking at - and the program's pi
        otherwise, so the box is never left with nothing to search. A stopped run
        computed nothing, so it is not a search target.
        """

        computation = self.computation
        if computation is not None and computation.complete and computation.decimals:
            return computation.decimals, "the run that last finished on this page"
        return pi.program_pi_decimals(), "the pi the program calculates with"

    def search_pattern(self) -> str:
        """The digits typed into the search field, with anything else dropped.

        The field carries a digits-only filter, but that filter is a Flutter-side
        convenience: a value that arrives another way - pasted on a platform whose
        filter differs, set by a test, restored by a rebuild - still has to read as
        digits before it can be searched for.
        """

        return NON_DIGITS.sub("", self.search_field.value or "")

    def refresh_search_state(self, e: object = None, paint: bool = True) -> None:
        """Keep the search box honest about what it holds and what it searches.

        ``paint`` is off while :meth:`build` is still assembling the tree, and from
        the handlers that repaint the page themselves once they are done.
        """

        del e
        typed = self.search_field.value or ""
        pattern = self.search_pattern()
        if pattern != typed:
            self.search_field.value = pattern
        self.search_button.disabled = not pattern
        decimals, source = self.search_target()
        self.search_scope.value = search_scope_text(decimals, source)
        if paint:
            self.page.update()

    def run_search(self, e: object = None) -> None:
        """Look the typed digits up in the decimals the page holds.

        The scan is a plain substring search over a string the page already holds,
        which is a C-level sweep even across a hundred million decimals - a fraction
        of a second, so it runs here rather than on a worker thread. It is the
        computation that needs a thread, not the reading of a number already computed.
        """

        del e
        decimals, source = self.search_target()
        self.search_scope.value = search_scope_text(decimals, source)
        pattern = self.search_pattern()
        self.search_field.value = pattern
        self.search_button.disabled = not pattern
        self.search_result.value = search_result_text(pattern, decimals, source)
        self.page.update()

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
        """Open the digits in a wrapping label that grows as it is read."""

        self._dialog_decimals = decimals
        self._dialog_loaded = 0
        self._dialog_loading = False
        window_width = getattr(self.page, "width", None)
        width = dialog_width(window_width)

        self._dialog_label = ft.Text(
            "",
            key="pi-digits-label",
            size=DIALOG_FONT_SIZE,
            selectable=True,
            width=width,
        )
        self._dialog_scrollbox = ft.ListView(
            controls=[self._dialog_label],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            on_scroll=self._on_digits_scroll,
            key="pi-digits-list",
        )
        self._dialog_count = ft.Text(size=11, color=styles.TEXT_FAINT, selectable=True)
        self._append_digits(paint=False)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(heading, size=18),
                content=ft.Column(
                    [
                        self._dialog_scrollbox,
                        self._dialog_count,
                    ],
                    spacing=8,
                    height=DIALOG_VIEWPORT_HEIGHT,
                    width=width,
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

    def _dialog_footline(self) -> str:
        """How much of the number the label currently holds.

        The reader loads digits by scrolling at them, so the footer says what is there
        and what is still to come - and says it differently
        once it is the ceiling rather than the end of the number that stops the list.
        """

        total = len(self._dialog_decimals)
        loaded = self._dialog_loaded
        if loaded >= total:
            return f"all {total:,} decimals on screen"
        if loaded >= dialog_load_ceiling(total):
            return (
                f"decimals 1 to {loaded:,} of {total:,} - that is as far as this "
                "dialog scrolls; the button below copies every decimal of it"
            )
        return (
            f"decimals 1 to {loaded:,} of {total:,} on screen - keep scrolling for "
            f"the next {DIALOG_BATCH_DECIMALS:,}"
        )

    def _append_digits(self, paint: bool = True) -> None:
        """Append the next batch of decimals to the label.

        The same label stays in the scrollbox as its text grows. The footer is updated
        with each batch, including when the last batch reaches the end or the limit.
        """

        start, end = dialog_batch_range(self._dialog_decimals, self._dialog_loaded)
        if end > start:
            self._dialog_label.value = f"3.{self._dialog_decimals[:end]}"
            self._dialog_loaded = end
        self._dialog_count.value = self._dialog_footline()
        if paint and end > start:
            self.page.update()

    def _on_digits_scroll(self, e: object) -> None:
        """Load the next batch once the reader nears the end of the loaded digits.

        One drag arrives as a burst of scroll notifications, which is harmless rather
        than wasteful: as soon as a batch goes in, the bottom of the number is another
        :data:`DIALOG_BATCH_DECIMALS` decimals away again, so the next notification is
        nowhere near it. The guard is for notifications that land while a batch is
        being built, which would otherwise stack up over the same slice of the number.
        """

        if self._dialog_loading:
            return
        if self._dialog_loaded >= dialog_load_ceiling(len(self._dialog_decimals)):
            return
        if not self._scrolled_near_bottom(e):
            return

        self._dialog_loading = True
        try:
            self._append_digits()
        finally:
            self._dialog_loading = False

    def _scrolled_near_bottom(self, e: object) -> bool:
        """Whether the scrollbox reports that its end is near."""

        extent_after = getattr(e, "extent_after", None)
        return (
            extent_after is not None
            and float(extent_after) <= DIALOG_LOAD_AHEAD_PIXELS
        )
