"""The filter every dropdown in the app offers over its own option list.

The unit menus are the reason it exists: ``conversions.yaml`` runs to 2778 lines
of units, and scrolling a dropdown to reach "teaspoon" is losing. Flet's client
(``packages/flet/lib/src/controls/dropdown.dart``) hands ``enable_filter``
straight to Flutter's ``DropdownMenu``, whose default predicate is a
case-insensitive substring match on the option's label - which in this app is the
option ``text``, so a unit's name *and* its symbol are searchable and the query is
matched as plain text, never as a regex. Flutter's ``filterCallback`` is not
exposed by Flet, so the predicate cannot be replaced.

``editable`` is not decoration either: the Dart maps it to the field's focus node
and Flutter renders the field read-only whenever it cannot take focus, so with the
default ``editable=False`` there is nothing to type and ``enable_filter`` does
nothing at all. That is the whole of :func:`searchable` - the flags - plus
:func:`settle_typed_query`, which pays for the one thing an editable field makes
possible: being left holding words that name no option.
"""

from dataclasses import dataclass
from typing import Callable, Protocol, cast

import flet as ft


class _Updater(Protocol):
    """Whatever :func:`searchable` can repaint - the app's pages and the page
    stand-ins the tests build. Only the no-argument form is ever called."""

    def update(self) -> None: ...


@dataclass(frozen=True)
class ResolvedPick:
    """The event handed to a dropdown's own ``on_select`` handler when a typed
    query is resolved into a selection.

    A pick the app resolved has to do what a pick the user made does - re-convert,
    re-plan, re-theme - and the only way to make that happen is to run the handler
    the control already holds. Every such handler in this app ignores its argument,
    so a control-carrying event is all it needs.
    """

    control: ft.Dropdown


def option_label(option: ft.DropdownOption) -> str:
    """The words an option shows - what Flutter's filter matches against.

    Options whose text is a control rather than a string fall back to their key,
    which is what the app can match on anyway.
    """

    text = option.text
    if isinstance(text, str):
        return text
    return str(option.key or "")


def selected_label(dropdown: ft.Dropdown) -> str:
    """The words the dropdown currently shows for its selection."""

    for option in dropdown.options:
        if option.key == dropdown.value:
            return option_label(option)
    return ""


def show_selection(dropdown: ft.Dropdown, page: _Updater) -> None:
    """Put the current selection's words back into an edited field.

    The Dart rewrites the field text only when the Python ``value`` *changes*, so
    an unchanged value has to be taken away and handed back for the text to
    follow - one update each, or the two changes cancel out in a single delta.
    """

    selection = dropdown.value
    dropdown.value = None
    page.update()
    dropdown.value = selection
    page.update()


def settle_typed_query(dropdown: ft.Dropdown, page: _Updater, query: str) -> None:
    """Make a dropdown that has just lost focus say what it actually holds.

    Typing into an editable dropdown filters its menu but changes no selection, so
    the field can be left holding a query while ``value`` still names the old
    option. On blur:

    * a query naming exactly one option becomes that selection, and the dropdown's
      own ``on_select`` handler runs for it;
    * any other query - nothing typed, several options matching, none matching -
      leaves the selection alone and puts its words back in the field, so what is
      on screen is always what is chosen.
    """

    query = query.strip()
    if not query or query.casefold() == selected_label(dropdown).casefold():
        return

    matches = [
        option
        for option in dropdown.options
        if query.casefold() in option_label(option).casefold()
    ]
    if len(matches) == 1:
        key = matches[0].key
        if key is not None and key != dropdown.value:
            dropdown.value = key
            handler = cast(Callable[[object], None] | None, dropdown.on_select)
            if handler is not None:
                handler(ResolvedPick(control=dropdown))
        return

    show_selection(dropdown, page)


def searchable(
    dropdown: ft.Dropdown, page: _Updater, *, search_icon: bool = False
) -> ft.Dropdown:
    """Give a dropdown the built-in filter and the rule that keeps it honest.

    ``search_icon`` puts the magnifier inside the field, which is worth its space
    where the option list is long enough to need searching and is left out
    elsewhere so a three-choice settings box keeps looking like a box.

    Whatever ``on_text_change`` / ``on_blur`` handlers the dropdown already carried
    are kept and still run, the way :meth:`AnycalcApp.watch_field_focus` keeps a
    text field's own focus handlers.
    """

    already_changed = cast(
        Callable[[object], None] | None, dropdown.on_text_change
    )
    already_blurred = cast(Callable[[object], None] | None, dropdown.on_blur)
    # The query is kept here because the blur event does not carry it and the
    # Python-side ``text`` is only refreshed while a text-change handler exists.
    query: dict[str, str] = {"text": ""}

    def remember_query(event) -> None:
        query["text"] = str(getattr(event.control, "text", "") or "")
        if already_changed is not None:
            already_changed(event)

    def resolve_query(event) -> None:
        settle_typed_query(dropdown, page, query["text"])
        if already_blurred is not None:
            already_blurred(event)

    dropdown.enable_filter = True
    dropdown.editable = True
    if search_icon:
        dropdown.leading_icon = ft.Icons.SEARCH
    dropdown.on_text_change = remember_query
    dropdown.on_blur = resolve_query
    return dropdown


def has_filter(dropdown: ft.Dropdown) -> bool:
    """Whether this dropdown offers the filter - what the tests assert."""

    return bool(dropdown.enable_filter) and bool(dropdown.editable)
