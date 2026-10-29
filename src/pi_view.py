"""The pi page: choose how many digits, compute them, and use them everywhere.

Computing pi is the one calculation in this app that can take longer than a
person wants to wait, so the page is built around that: a digit count anywhere
from 3 to 100 million, a progress bar with percentage, terms, speed and a finish
estimate under it, a Stop button, and a "Use this value for the program" button
that makes the finished digits the pi every calculation in the app multiplies by.

The run happens on a worker thread, so the pad stays responsive, and the page
only repaints a few times a second no matter how many terms the series runs. The
digits are shown in a dialog that starts with a handful of lines and appends more
as the user scrolls - a hundred million digits are never put on screen at once,
which is what would make the app lag or die.
"""

import threading
from time import monotonic
from typing import Callable, Optional

import flet as ft

import pi
import pi_value
from pi_value import PiComputation, PiProgress, format_duration
from styles import (
    ACCENT,
    CARD_BACKGROUND,
    TEXT_ERROR,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_SOFT,
)

# How much of a finished run the result card shows; the rest is in the dialog.
CARD_DECIMALS = 120
CURRENT_DECIMALS = 40

# A run of a hundred million digits reports progress millions of times; the page
# repaints at most this often so the bar cannot starve the app.
PROGRESS_PAINT_SECONDS = 0.05

# The digits dialog: 60 decimals to a line (that is what fits the dialog width in
# a monospace font at this size), more lines than the viewport holds straight away
# so there is always something to scroll, then more lines as the reader approaches
# the end of what has been built. The line height is handed to the ListView as
# `item_extent`, so Flutter only ever renders the lines inside the viewport - a
# dialog extended to a million lines scrolls as cheaply as one with ten.
DIALOG_LINE_DIGITS = 60
DIALOG_LINE_HEIGHT = 18
DIALOG_VIEWPORT_LINES = 18
DIALOG_INITIAL_LINES = 24
DIALOG_CHUNK_LINES = 40

# Every line is tagged with the decimal it starts at, right-aligned in this wide
# gutter, so the reader of a long run always knows where they are in the number.
DIALOG_INDEX_GUTTER = 9

# Extend only once the reader is this close to the bottom of the built lines, so
# scrolling back up through a long dialog costs nothing.
DIALOG_FILL_AHEAD_LINES = 12


def percent_text(percent: float) -> str:
    """A percentage with no pointless decimal: ``0%``, ``12.3%``, ``100%``."""

    text = f"{percent:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"


class PiView:
    """The pi calculation page.

    :param page: the page the form is shown on - used to update it and to open the
        digits dialog.
    :param make_copy_button: the app's shared copy-button factory.
    """

    def __init__(
        self,
        page: ft.Page,
        make_copy_button: Callable[..., ft.IconButton],
    ) -> None:
        self.page = page
        self.make_copy_button = make_copy_button

        self.computation: Optional[PiComputation] = None
        self.progress: Optional[PiProgress] = None
        self.running = False
        self.cancel = threading.Event()
        self._last_paint = 0.0
        self._dialog_shown = 0
        self._dialog_decimals = ""
        self._dialog_lines: Optional[ft.ListView] = None

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
        )
        self.digits_field = ft.TextField(
            key="pi-digits-exact",
            label="Exact number of digits (optional)",
            hint_text=f"{pi.MIN_PI_DIGITS:,} - {pi.MAX_PI_DIGITS:,}",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self.refresh_plan,
        )
        self.plan_text = ft.Text(size=11, color=TEXT_FAINT, key="pi-plan")

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
            bgcolor=CARD_BACKGROUND,
            bar_height=8,
            border_radius=4,
        )
        self.percent_text = ft.Text(
            "0%", size=13, weight=ft.FontWeight.BOLD, key="pi-percent"
        )
        self.terms_text = ft.Text("", size=11, color=TEXT_MUTED, key="pi-terms")
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
                    self.view_current_button,
                ),
                ft.Row([self.digits_dropdown, self.digits_field], spacing=12),
                self.plan_text,
                ft.Row([self.compute_button, self.stop_button], spacing=10),
                self._card(
                    self.progress_bar,
                    ft.Row(
                        [self.percent_text, self.terms_text],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
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

        self.compute_button.disabled = True
        self.stop_button.disabled = False
        self.view_button.disabled = True
        self.adopt_button.disabled = True

        self.progress_bar.value = 0.0
        self.percent_text.value = "0%"
        self.terms_text.value = f"0 / {pi.pi_term_count(digits):,} terms"
        self.speed_text.value = "speed -"
        self.estimate_text.value = "estimate -"
        self.result_text.value = ""
        self.status_text.value = f"computing {digits:,} decimals ..."
        self.page.update()

        # Flet's own background-thread API rather than a bare threading.Thread: the
        # worker gets this page bound to its context, and on a web build - where
        # Python threads are not available - it runs inline instead of dying.
        self.page.run_thread(self._run, digits)

    def stop_run(self, e=None) -> None:
        """Ask a running computation to stop at its next term."""

        del e
        if not self.running:
            return
        self.cancel.set()
        self.stop_button.disabled = True
        self.status_text.value = "stopping after the current term ..."
        self.page.update()

    def _run(self, digits: int) -> None:
        """The worker thread body: compute, then hand the outcome to the page.

        Progress is reported from inside the binary split - millions of times for a
        hundred million digits - so :meth:`_paint_progress` is rate-limited and this
        thread never touches a control more often than the page can be repainted.
        """

        def on_progress(progress: PiProgress) -> None:
            self.progress = progress
            now = monotonic()
            if now - self._last_paint < PROGRESS_PAINT_SECONDS:
                return
            self._last_paint = now
            self._paint_progress()

        try:
            computation = pi_value.compute_pi(
                digits, on_progress=on_progress, cancel_check=self.cancel.is_set
            )
        except Exception as error:  # a failed run must not leave the page waiting
            self.running = False
            self.computation = None
            self.status_text.value = f"could not compute pi: {error}"
            self._finish_run_controls()
            self.page.update()
            return

        self.running = False
        self.computation = computation
        if computation.cancelled:
            stopped = self.progress
            where = (
                f"{stopped.terms_done:,} of {stopped.terms_total:,} terms"
                if stopped
                else "no terms"
            )
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
        """Push the running numbers into the progress card."""

        progress = self.progress
        if progress is None:
            return
        self.progress_bar.value = progress.fraction
        self.percent_text.value = percent_text(progress.percent)
        self.terms_text.value = (
            f"{progress.terms_done:,} / {progress.terms_total:,} terms"
        )
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
        self.status_text.value = (
            f"the program now calculates with pi to "
            f"{pi.program_pi_digits():,} decimals"
        )
        self.page.update()

    def refresh_current(self) -> None:
        """Show the pi the program is calculating with right now."""

        digits = pi.program_pi_digits()
        self.current_text.value = pi.format_pi_digits(
            pi.program_pi_text(), digits, CURRENT_DECIMALS
        )
        self.current_note.value = f"{digits:,} decimals, computed by this app"
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
        """Open the digits, a few lines at a time.

        A finished run can be a hundred million digits long, and putting that many
        text controls on the screen at once is exactly what would make the app lag
        or die. The dialog therefore starts with :data:`DIALOG_INITIAL_LINES` lines
        and :meth:`_fill_more_on_scroll` extends it while the user scrolls. The list
        also gets ``item_extent``, so the Flutter side only ever renders the lines
        inside the viewport even after millions have been added.
        """

        self._dialog_decimals = decimals
        # Never build more lines than the digits actually fill: a twelve-decimal pi
        # is one line, not a screenful of empty ones.
        total_lines = -(-len(decimals) // DIALOG_LINE_DIGITS)
        first_lines = min(DIALOG_INITIAL_LINES, total_lines)

        self._dialog_note = ft.Text(
            f"{DIALOG_LINE_DIGITS} decimals to a line - keep scrolling and more "
            "of the number loads.",
            size=11,
            color=TEXT_MUTED,
        )
        self._dialog_lines = ft.ListView(
            controls=[self._dialog_line(index) for index in range(first_lines)],
            item_extent=DIALOG_LINE_HEIGHT,
            build_controls_on_demand=True,
            scroll=ft.ScrollMode.AUTO,
            on_scroll=self._fill_more_on_scroll,
            key="pi-digits-list",
        )
        self._dialog_shown = first_lines
        self._dialog_count = ft.Text(self._dialog_footline(), size=11, color=TEXT_FAINT)
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(heading, size=18),
                content=ft.Column(
                    [
                        self._dialog_note,
                        ft.Container(
                            content=self._dialog_lines,
                            height=DIALOG_VIEWPORT_LINES * DIALOG_LINE_HEIGHT,
                            bgcolor=CARD_BACKGROUND,
                            border_radius=8,
                            padding=6,
                        ),
                        self._dialog_count,
                    ],
                    spacing=8,
                    width=560,
                ),
                actions=[
                    self.make_copy_button(
                        lambda: f"3.{decimals}", tooltip="Copy all digits"
                    ),
                    ft.TextButton(
                        content="Close", on_click=lambda: self.page.pop_dialog()
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )
        self.page.update()

    def _dialog_line(self, index: int) -> ft.Text:
        """One line of the dialog: the digits, tagged with where they start."""

        start = index * DIALOG_LINE_DIGITS
        chunk = self._dialog_decimals[start : start + DIALOG_LINE_DIGITS]
        return ft.Text(
            f"{start + 1:>{DIALOG_INDEX_GUTTER}}  {chunk}",
            size=12,
            font_family="monospace",
            no_wrap=True,
        )

    def _dialog_footline(self) -> str:
        shown = self._dialog_shown * DIALOG_LINE_DIGITS
        total = len(self._dialog_decimals)
        if shown >= total:
            return f"all {total:,} decimals on screen"
        return f"showing the first {shown:,} of {total:,} decimals - scroll for more"

    def _fill_more_on_scroll(self, e: ft.OnScrollEvent) -> None:
        """Add lines as the reader nears the end of what has been built.

        The scroll event says how much built content is still below the viewport
        (``extent_after``), so the dialog extends only when the reader is within
        :data:`DIALOG_FILL_AHEAD_LINES` lines of the bottom of the lines it holds -
        scrolling back up through a long dialog therefore costs nothing. Each batch
        is :data:`DIALOG_CHUNK_LINES` lines, which is what keeps a run of a hundred
        million decimals responsive instead of loading it all at once.
        """

        decimals = getattr(self, "_dialog_decimals", "")
        if not decimals or self._dialog_shown * DIALOG_LINE_DIGITS >= len(decimals):
            return

        try:
            below = float(e.extent_after)
        except (TypeError, ValueError):  # a notification without geometry
            below = 0.0
        if below > DIALOG_FILL_AHEAD_LINES * DIALOG_LINE_HEIGHT:
            return

        # The lines that exist - ceiling division, so a run whose decimals do not
        # fill the last line still gets that line. Never build past it.
        total_lines = -(-len(decimals) // DIALOG_LINE_DIGITS)
        up_to = min(self._dialog_shown + DIALOG_CHUNK_LINES, total_lines)

        self._dialog_lines.controls.extend(
            self._dialog_line(index) for index in range(self._dialog_shown, up_to)
        )
        self._dialog_shown = up_to
        self._dialog_count.value = self._dialog_footline()
        self.page.update()

