"""Integration tests - the built app, driven the way a user drives it.

Run them with ``flet test`` (``flet test -k app`` selects only this file). Every
test gets a *fresh instance of the real app* - Flet packages ``src/`` into a
monolithic build with an embedded Python and runs that, while this file runs on
the host and pokes the app over a separate channel. So these tests cover the
wiring a user actually touches: the drawer, the conversion page, the live chain,
the keypad.

A few things about the Flet 1.0.5 tester were learned the hard way and are worth
knowing before adding a test here:

* ``key`` only reaches some controls. The calculator's text buttons and the
  conversion form's fields are found with ``find_by_key``, but a
  ``NavigationDrawerDestination`` and a ``Dropdown``'s options never are - drawer
  entries have to be tapped by their label text, and picking an arbitrary From/To
  pair cannot be driven from a UI test at all, so the unit pairs are covered
  instead by the exhaustive route tests in ``tests/test_conversion_engine.py``.
  Reversing the pair that the page already opens on is reachable, through the
  form's swap button (``conversion-swap``). A ``Switch`` is another control whose
  key never resolves - ``find_by_key("settings-memory-keys")`` finds nothing. Its
  sentence is not even the switch's own label any more - a switch label is laid out
  on one line and gets cut off, so the words are a separate ``Text`` with its own
  click handler - which makes it findable with ``find_by_text_containing``, and
  tapping it flips the switch; that is how ``flip_memory_keys_switch`` drives it.
* The drawer is still closing when ``open_page`` returns, so the first tap after
  it can be spent dismissing the drawer instead of reaching its target. A helper
  that opens something over the calculator has to press its button again when the
  expected dialog is not on screen - see ``flip_memory_keys_switch``.
* A ``Dropdown``'s option texts *are* findable with ``find_by_text`` even while
  its menu is closed, which inflates those counts: an option matches once per
  dropdown that offers it, plus one more time for the option a dropdown is
  currently displaying (the settings test reads the selected theme back that way,
  and a color name matching twice proves both color pickers list it). Matching is
  exact, never substring - ``find_by_text("MODE")`` finds nothing while the
  "REGULAR MODE" caption is on screen; ``find_by_text_containing`` is for that.
  The menu has to be opened by tapping the dropdown first, and the row that is
  actually on screen is **not** the ``.last`` match on Flet 1.1: 1.1 renders a
  ``Dropdown`` as Material 3 ``DropdownMenu``, and the menu row now sits right
  after the open dropdown's own offstage copy - index ``1`` for the settings color
  dropdowns, which is what ``test_settings_applies_…`` taps. Tapping ``.last``
  there hits another dropdown's offstage copy and can land on a different row;
  index 0 is an offstage copy too. Flet 1.1 paints all 32 palette entries into the
  finder tree, but entries outside the menu's visible viewport are not tappable.
  The picker entry is above that viewport when the menu opens on the default Blue
  selection, so the drive-through selects a visible named color instead; the
  settings unit tests cover the picker reveal. A dropdown hidden with
  ``visible=False`` paints nothing, so none of its option texts are findable either
  - that is how the settings test reads the color dropdowns being hidden until the
  Custom theme is picked. Revealing a control *inside* a group that is already on
  screen is the one case a ``visible`` flag does not cover on Flet 1.1: measured
  with a probe, the flag, the text and a pushed ``page.update`` were all correct
  and the ``Text`` still never appeared. The app therefore adds the color caption
  and its picker to the group's column - and takes them out again - rather than
  hiding them, so the caption assertions below read a child-list change.
* ``flet test`` runs the real app against the real app-data directory
  (``…/.local/share/com.github.greentruck50.anycalc``, the same one ``flet run``
  uses), and the app saves its theme, colors and history there. A test therefore
  must never assume it opens on the defaults - an earlier run, or the developer's
  own session, may have left other settings in that file - it has to put the
  state it goes on to assert into place first, which is why the settings test
  taps "Reset to defaults" before it reads any dropdown.
* A keypad key that exists in both the scientific rows and the regular rows is
  found *twice*, because scientific mode renders the regular rows underneath its
  own. The pad keeps every key exactly once (``(`` and ``)`` used to be
  duplicated there), so a ``find_by_key`` count of 1 stays meaningful.
* Only rendered controls are found, so assertions read the chain cards (plain
  ``Text``) rather than the read-only Result field. And the converse has a
  catch: a control hidden with ``visible=False`` stays in the finder tree, so
  "the chain disappeared" has to be asserted on the hop texts the app actually
  removes - never on the "Chain of operations" header, which only gets hidden.
* A ``Finder`` has no ``.value`` and there is no ``tester.get``, so a control's
  content can never be read back - assertions are only about which texts and
  keys are findable. The keypad tests therefore read the live answer preview (a
  plain ``Text``) and prove "=" committed by the caption flipping from
  ``EXPRESSION`` to ``RESULT``.
* ``flet_app.resize_page`` raises ``RuntimeError('page is not initialized')`` on
  this version, so a test cannot set its own window size; the default desktop
  window is tall enough for the pages used here.
* The Value field is a ``KeyboardType.NUMBER`` field, so the tester cannot type a
  half-typed number into it - ``"3."`` arrives as ``"3"``. Clearing the field is
  the UI path that reaches the app's "quietly clear result and chain" branch;
  the parse-failure branch (a value that is neither empty nor a number) is not
  reachable from a desktop test and is deliberately left untested here.
* Screenshot goldens are Android/iOS only, so there are none here.
* ``find_by_text_containing`` matches inside a *rendered span*, so a string that
  spans a line wrap in a long ``Text`` is never found. Assertions on the unit
  guidance notes therefore use short fragments, never a whole sentence.
* The drawer's entries live in a list that scrolls, and only the ones inside the
  window height get rendered, so a conversion group low enough in that list cannot
  be opened from a UI test at all - the tester has neither scroll nor drag. Such a
  page test is skipped with a reason instead of failing (as the Force one is), and
  the group stays covered by the engine tests.
"""

import flet.testing as ftt
import pytest
from flet.testing.remote_tester import RemoteTester

from conversions import load_conversion_config

UNIT_GROUPS, _ = load_conversion_config()
UNIT_LABELS = {
    unit["id"]: f"{unit['name']} ({unit['symbol']})"
    for group in UNIT_GROUPS
    for unit in group["units"]
}
TestDriver = ftt.Tester | RemoteTester


def hop_line(source_id: str, target_id: str, index: int = 1) -> str:
    """The heading a chain card prints for one hop."""

    return f"{index}. {UNIT_LABELS[source_id]} → {UNIT_LABELS[target_id]}"


async def open_page(tester: TestDriver, label: str) -> None:
    """Open the drawer and select the entry with this label.

    Only entries the window height actually renders can be found - the drawer's
    list scrolls, but the remote tester has no scroll or drag, so an entry past
    the fold is out of reach for a UI test. See the skip on the Force page test.
    """

    await tester.tap(await tester.find_by_key("menu-button"))
    await tester.pump_and_settle()
    destination = await tester.find_by_text(label)
    assert destination.count == 1, f"{label!r} is not in the drawer"
    await tester.tap(destination.first)
    await tester.pump_and_settle()


async def flip_memory_keys_switch(tester: TestDriver) -> None:
    """Flip the Settings switch that swaps the scientific pad's shared row.

    The switch and its words are the second entry of the Settings column, so they
    are always inside that dialog's viewport, but a ``Switch`` is one of the
    controls whose ``key`` the tester cannot reach - the sentence beside the toggle
    is what can be found and tapped, and its own click handler flips the switch. A
    ``Finder`` cannot read a switch back either, so this only flips it; what the
    setting did is read off the pad by ``show_memory_row``.

    The drawer left open by ``open_page`` swallows the first tap, so the button is
    pressed again if the dialog did not appear.
    """

    for attempt in (1, 2):
        await tester.tap(await tester.find_by_key("settings-button"))
        await tester.pump_and_settle()
        if (await tester.find_by_text("Settings")).count == 1:
            break
        assert attempt == 1, "the Settings dialog never opened"
    switch = await tester.find_by_text_containing("Memory keys")
    assert switch.count == 1, "the memory-keys switch is not in the dialog"
    await tester.tap(switch.first)
    await tester.pump_and_settle()
    await tester.tap(await tester.find_by_key("settings-close"))
    await tester.pump_and_settle()


async def show_memory_row(tester: TestDriver, wanted: bool) -> None:
    """Put the scientific pad's shared row where a test needs it.

    Call it with the Scientific Calculator showing. The pad says which row it
    carries: that row holds ``MCLR`` while the memory keys are up and
    ``Set Variable`` while the variable keys are. Normalising first is not
    optional - the app restores its settings from the real app-data directory, so
    an earlier run or a developer's own session may have left the switch on.
    """

    memory_row_on_pad = (await tester.find_by_key("key-MCLR")).count == 1
    if memory_row_on_pad != wanted:
        await flip_memory_keys_switch(tester)
    assert (await tester.find_by_key("key-MCLR")).count == int(wanted)


async def test_volume_conversion_page_converts_as_you_type(
    flet_app: ftt.FletTestApp,
) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Volume Conversion")

    # The conversion form replaced the calculator in the content area.
    assert (await tester.find_by_key("conversion-value")).count == 1
    assert (await tester.find_by_key("conversion-from")).count == 1
    assert (await tester.find_by_key("conversion-to")).count == 1
    assert (await tester.find_by_key("conversion-result")).count == 1
    assert (
        await tester.find_by_text("Converts as you type or change units")
    ).count == 1

    # The page opens on the group's first two units, mm3 -> cm3, and 1000 mm3
    # is exactly 1 cm3 - no rounding artifact may show up.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "1000")
    await tester.pump_and_settle()

    assert (await tester.find_by_text("CHAIN OF OPERATIONS (1 step)")).count == 1
    assert (
        await tester.find_by_text(
            hop_line("volume_cubic_millimeter", "volume_cubic_centimeter")
        )
    ).count == 1
    assert (await tester.find_by_text("1000 → 1")).count == 1

    # Both units this page opens on carry a guidance note, so the note block is
    # visible without touching a dropdown. Assert on short fragments: a long
    # guidance line wraps, and the finder only matches inside one rendered span.
    assert (await tester.find_by_text("UNIT GUIDANCE")).count == 1
    assert (await tester.find_by_text_containing("Exactly 1 µL")).count == 1
    assert (await tester.find_by_text_containing("Exactly 1 mL")).count == 1


async def test_weight_conversion_page_converts_as_you_type(
    flet_app: ftt.FletTestApp,
) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Weight Conversion")
    assert (await tester.find_by_key("conversion-value")).count == 1

    # ug -> mg is that group's default pair: 1 ug must read as exactly 0.001 mg.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "1")
    await tester.pump_and_settle()

    assert (await tester.find_by_text("1 → 0.001")).count == 1
    assert (
        await tester.find_by_text(hop_line("weight_microgram", "weight_milligram"))
    ).count == 1

    # No Weight unit carries a guidance line, so no note block is shown there.
    assert (await tester.find_by_text("UNIT GUIDANCE")).count == 0


async def test_area_conversion_page_converts_as_you_type(
    flet_app: ftt.FletTestApp,
) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Area Conversion")
    assert (await tester.find_by_key("conversion-value")).count == 1

    # mm2 -> cm2 is that group's default pair: 100 mm2 must read as exactly 1 cm2.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "100")
    await tester.pump_and_settle()

    assert (await tester.find_by_text("100 → 1")).count == 1
    assert (
        await tester.find_by_text(
            hop_line("area_square_millimeter", "area_square_centimeter")
        )
    ).count == 1


async def test_energy_conversion_page_converts_as_you_type(
    flet_app: ftt.FletTestApp,
) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Energy Conversion")
    assert (await tester.find_by_key("conversion-value")).count == 1

    # joule -> kilojoule is that group's default pair: 1000 J must read as 1 kJ.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "1000")
    await tester.pump_and_settle()

    assert (await tester.find_by_text("1000 → 1")).count == 1
    assert (
        await tester.find_by_text(hop_line("energy_joule", "energy_kilojoule"))
    ).count == 1

    # Both default units carry a guidance note, so the block shows unasked.
    assert (await tester.find_by_text("UNIT GUIDANCE")).count == 1
    assert (await tester.find_by_text_containing("one newton acting")).count == 1
    assert (await tester.find_by_text_containing("food label")).count == 1


@pytest.mark.skip(
    reason="'Force Conversion' is the ninth drawer entry and the drawer list is "
    "taller than the host window, so that entry never renders - the test host has "
    "neither scroll nor drag, so the page cannot be opened from a UI test. Its "
    "arithmetic is covered by the Force sweep and reference values in "
    "tests/test_conversion_engine.py."
)
async def test_force_conversion_page_converts_as_you_type(
    flet_app: ftt.FletTestApp,
) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Force Conversion")
    assert (await tester.find_by_key("conversion-value")).count == 1

    # newton -> kilonewton is that group's default pair: 1000 N must read as 1 kN.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "1000")
    await tester.pump_and_settle()

    assert (await tester.find_by_text("1000 → 1")).count == 1
    assert (
        await tester.find_by_text(hop_line("force_newton", "force_kilonewton"))
    ).count == 1

    assert (await tester.find_by_text("UNIT GUIDANCE")).count == 1
    assert (await tester.find_by_text_containing("accelerates 1 kg")).count == 1
    assert (await tester.find_by_text_containing("bolt, rope")).count == 1


@pytest.mark.skip(
    reason="'Pi Calculation' is the entry under 'Other' at the bottom of the "
    "drawer, i.e. below the last conversion, and the drawer list is taller than "
    "the host window - that entry never renders, and the test host has neither "
    "scroll nor drag, so the page cannot be opened from a UI test. The whole "
    "feature is covered engine-side in tests/test_pi_engine.py instead."
)
async def test_pi_page_computes_and_adopts_a_value(
    flet_app: ftt.FletTestApp,
) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Pi Calculation")
    assert (await tester.find_by_key("pi-digits")).count == 1
    assert (await tester.find_by_key("pi-compute")).count == 1

    # The startup pi is already on the page: 12 decimals this app computed itself.
    assert (
        await tester.find_by_text_containing("3.141592653589")
    ).count >= 1

    compute_button = await tester.find_by_key("pi-compute")
    await tester.tap(compute_button.first)
    await tester.pump_and_settle()

    assert (await tester.find_by_text("100%")).count == 1
    assert (
        await tester.find_by_text_containing(
            "3.1415926535897932384626433832795028841971693993751"
        )
    ).count == 1

    adopt_button = await tester.find_by_key("pi-adopt")
    await tester.tap(adopt_button.first)
    await tester.pump_and_settle()
    assert (
        await tester.find_by_text_containing("calculates with pi to 12 decimals")
    ).count == 1


async def test_settings_applies_as_it_is_picked_and_resets_to_defaults(
    flet_app: ftt.FletTestApp,
) -> None:
    """A settings choice lands the moment it is picked, and "Reset to defaults"
    puts the defaults back - both while the dialog stays open, since there is no
    Apply button left to press. The color dropdowns belong to the Custom theme,
    so they only appear once that theme is picked."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    async def shown(label: str) -> int:
        """Times an exact label is painted, once the screen has stopped moving.

        A closed Dropdown keeps one copy of every option's text per dropdown that
        offers it, plus one extra copy of the option it is currently displaying.
        So a theme name matching twice means that dropdown shows it. A dropdown
        hidden with visible=False paints nothing at all, which is how the hidden
        color settings are read here. The settings dialog builds 32 options per
        color dropdown, so pump until the count stops changing before reading it.
        """

        previous = -1
        for _ in range(6):
            await tester.pump_and_settle()
            count = (await tester.find_by_text(label)).count
            if count == previous:
                break
            previous = count
        return previous

    await tester.tap(await tester.find_by_key("settings-button"))
    await tester.pump_and_settle()
    assert (await tester.find_by_key("settings-theme-dropdown")).count == 1

    # Nothing waits for an Apply button any more: the dialog only offers Close and
    # "Reset to defaults".
    assert (await tester.find_by_text("Apply")).count == 0
    assert (await tester.find_by_text("Reset to defaults")).count == 1

    # The app remembers what an earlier run left in its data file, so the test
    # starts from reset - which doubles as proof that reset lands the defaults
    # immediately: they show up in the dropdowns of the dialog that stays open.
    await tester.tap(await tester.find_by_key("settings-reset"))
    await tester.pump_and_settle()
    assert (await tester.find_by_text("Settings")).count == 1
    assert await shown("Dark") == 2
    assert await shown("Light") == 1
    assert await shown("High contrast") == 1

    # The color dropdowns - "Forest green" and "Dark green" are only ever listed
    # by those two - are hidden while a built-in theme is picked.
    assert await shown("Forest green") == 0

    # Picking the Custom theme brings them back, named palette and all.
    await tester.tap(await tester.find_by_key("settings-theme-dropdown"))
    await tester.pump_and_settle()
    await tester.tap((await tester.find_by_text("Custom")).last)
    await tester.pump_and_settle()
    assert (await tester.find_by_text("Settings")).count == 1
    assert await shown("Custom") == 2
    assert await shown("Forest green") == 2
    assert await shown("Dark green") == 2

    # The picker entry is above the menu's tappable viewport when it opens on
    # Blue. Select a visible named color here; unit tests cover the picker reveal.
    await tester.tap(await tester.find_by_key("settings-primary-color"))
    await tester.pump_and_settle()
    await tester.tap((await tester.find_by_text("Violet")).at(1))
    await tester.pump_and_settle()
    assert (await tester.find_by_text("Settings")).count == 1
    assert await shown("Violet") == 3

    # Reset puts the default theme and colors back in the same open dialog.
    await tester.tap(await tester.find_by_key("settings-reset"))
    await tester.pump_and_settle()
    assert (await tester.find_by_text("Settings")).count == 1
    assert await shown("Dark") == 2
    assert await shown("Forest green") == 0

    # Close is the only way out, and it only closes.
    await tester.tap(await tester.find_by_key("settings-close"))
    await tester.pump_and_settle()
    assert (await tester.find_by_text("Settings")).count == 0
    assert (await tester.find_by_key("display")).count == 1


async def test_editing_the_value_reconverts_and_clearing_it_stays_quiet(
    flet_app: ftt.FletTestApp,
) -> None:
    """The result always belongs to the value now in the field."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Volume Conversion")
    await tester.enter_text(await tester.find_by_key("conversion-value"), "1000")
    await tester.pump_and_settle()
    assert (await tester.find_by_text("1000 → 1")).count == 1

    # Retyping replaces the whole field and re-converts in place.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "3")
    await tester.pump_and_settle()
    assert (await tester.find_by_text("3 → 0.003")).count == 1
    assert (await tester.find_by_text("1000 → 1")).count == 0

    # An empty field clears result and chain without reporting anything.
    await tester.enter_text(await tester.find_by_key("conversion-value"), "")
    await tester.pump_and_settle()
    assert (
        await tester.find_by_text(
            hop_line("volume_cubic_millimeter", "volume_cubic_centimeter")
        )
    ).count == 0
    assert (await tester.find_by_text("3 → 0.003")).count == 0
    assert (await tester.find_by_text_containing("No conversion path")).count == 0


async def tap_swap(tester: TestDriver) -> None:
    """Press the conversion form's swap button once.

    The first pointer event the page receives after the app has replaced its
    content area - or re-rendered the chain - is consumed by the test host rather
    than reaching a control, so a press is dispatched twice and only the second is
    expected to land. Measured on Flet 1.0.5: one tap after a re-render leaves the
    page untouched, two taps turn the conversion around.
    """

    for _ in range(2):
        await tester.tap(await tester.find_by_key("conversion-swap"))
        await tester.pump_and_settle()


async def test_swap_button_turns_the_conversion_around(
    flet_app: ftt.FletTestApp,
) -> None:
    """The swap button exchanges From and To and re-converts the typed value."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Volume Conversion")
    assert (await tester.find_by_key("conversion-swap")).count == 1
    assert (await tester.find_by_text("Swap units")).count == 1

    await tester.enter_text(await tester.find_by_key("conversion-value"), "1000")
    await tester.pump_and_settle()
    assert (
        await tester.find_by_text(
            hop_line("volume_cubic_millimeter", "volume_cubic_centimeter")
        )
    ).count == 1

    await tap_swap(tester)

    # The page now converts the other way round, and the chain belongs to the
    # value that was already in the field: 1000 cm3 is 1 000 000 mm3.
    assert (
        await tester.find_by_text(
            hop_line("volume_cubic_centimeter", "volume_cubic_millimeter")
        )
    ).count == 1
    assert (
        await tester.find_by_text(
            hop_line("volume_cubic_millimeter", "volume_cubic_centimeter")
        )
    ).count == 0
    assert (await tester.find_by_text("1000 → 1000000")).count == 1
    assert (await tester.find_by_text("CHAIN OF OPERATIONS (1 step)")).count == 1


async def test_drawer_switches_to_the_scientific_calculator(
    flet_app: ftt.FletTestApp,
) -> None:
    """The drawer is the only navigation, and it rebuilds the keypad."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    assert (await tester.find_by_key("key-7")).count == 1
    assert (await tester.find_by_key("key-sin")).count == 0

    await open_page(tester, "Scientific Calculator")
    # Storage may leave the memory keys on this pad, and they replace the variable
    # keys - so put the row this test reads into place before reading it.
    await show_memory_row(tester, wanted=False)

    assert (await tester.find_by_key("key-sin")).count == 1
    assert (await tester.find_by_key("key-Set Variable")).count == 1
    assert (await tester.find_by_key("key-±")).count == 1
    assert (await tester.find_by_text("SCIENTIFIC MODE")).count == 1
    # the regular rows stay, so the digits are still there
    assert (await tester.find_by_key("key-7")).count == 1


async def test_the_memory_keys_replace_the_variable_keys(
    flet_app: ftt.FletTestApp,
) -> None:
    """One shared row: the memory keys or the variable keys, never both.

    The pad stays eight rows tall either way, and the stored number is listed on
    the line under the display - the line the variables use - which is the only
    sign the memory holds anything.
    """

    tester = flet_app.tester
    await tester.pump_and_settle()

    await open_page(tester, "Scientific Calculator")
    await show_memory_row(tester, wanted=False)

    assert (await tester.find_by_key("key-Set Variable")).count == 1
    assert (await tester.find_by_key("key-MCLR")).count == 0

    await show_memory_row(tester, wanted=True)

    assert (await tester.find_by_key("key-MCLR")).count == 1
    assert (await tester.find_by_key("key-M+")).count == 1
    assert (await tester.find_by_key("key-Set Variable")).count == 0
    assert (await tester.find_by_key("key-Insert Variable")).count == 0
    assert (await tester.find_by_key("key-Clear Variables")).count == 0

    for key in ("4", "M+"):
        await tester.tap(await tester.find_by_key(f"key-{key}"))
        await tester.pump_and_settle()
    assert (await tester.find_by_text("M = 4")).count == 1

    await tester.tap(await tester.find_by_key("key-MCLR"))
    await tester.pump_and_settle()
    assert (await tester.find_by_text("M = 4")).count == 0

    # Back to the variable keys, which is also the app's default.
    await show_memory_row(tester, wanted=False)
    assert (await tester.find_by_key("key-Set Variable")).count == 1


async def test_regular_calculator_keypad_still_works(
    flet_app: ftt.FletTestApp,
) -> None:
    """The calculator the conversion work sits on: presses produce an answer."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    for key in ("7", "×", "8"):
        await tester.tap(await tester.find_by_key(f"key-{key}"))
        await tester.pump_and_settle()

    # The live answer under the display box is a plain Text control.
    assert (await tester.find_by_text("56")).count >= 1

    await tester.tap(await tester.find_by_key("key-="))
    await tester.pump_and_settle()

    # "=" commits the answer and flips the caption above the display.
    assert (await tester.find_by_key("display")).count == 1
    assert (await tester.find_by_text("RESULT")).count == 1
    assert (await tester.find_by_text("EXPRESSION")).count == 0


async def test_regular_calculator_percent_key_and_sign_change(
    flet_app: ftt.FletTestApp,
) -> None:
    """The regular pad's "%" is a desk calculator's percent, "±" edits the number."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    # Both keys sit in the regular pad's utility row.
    assert (await tester.find_by_key("key-%")).count == 1
    assert (await tester.find_by_key("key-±")).count == 1

    # "200+10%" is 200 plus ten percent of 200, the way a physical calculator reads it.
    for key in ("2", "0", "0", "+", "1", "0", "%"):
        await tester.tap(await tester.find_by_key(f"key-{key}"))
        await tester.pump_and_settle()
    assert (await tester.find_by_text("220")).count >= 1

    # Pressing "=" commits it: the caption above the display flips to RESULT. The
    # answer itself is asserted from the live preview above - a Finder has no
    # ".value" on this tester version, so a field's content cannot be read back.
    await tester.tap(await tester.find_by_key("key-="))
    await tester.pump_and_settle()
    assert (await tester.find_by_key("display")).count == 1
    assert (await tester.find_by_text("RESULT")).count == 1
    assert (await tester.find_by_text("EXPRESSION")).count == 0

    await tester.tap(await tester.find_by_key("key-AC"))
    await tester.pump_and_settle()

    # "5%" on its own simply divides by a hundred.
    for key in ("5", "%"):
        await tester.tap(await tester.find_by_key(f"key-{key}"))
        await tester.pump_and_settle()
    assert (await tester.find_by_text("0.05")).count >= 1

    await tester.tap(await tester.find_by_key("key-AC"))
    await tester.pump_and_settle()

    # "±" negates the number typed so far and keeps working as an operator follows.
    for key in ("5", "±", "×", "3"):
        await tester.tap(await tester.find_by_key(f"key-{key}"))
        await tester.pump_and_settle()
    assert (await tester.find_by_text("-15")).count >= 1

    # Pressing it again removes the sign instead of stacking another one.
    await tester.tap(await tester.find_by_key("key-±"))
    await tester.pump_and_settle()
    assert (await tester.find_by_text("15")).count >= 1
    assert (await tester.find_by_text("-15")).count == 0


async def test_scientific_calculator_percent_key_is_modulo(
    flet_app: ftt.FletTestApp,
) -> None:
    """The scientific pad keeps the programmer's "%" as the modulo operator."""

    tester = flet_app.tester
    await tester.pump_and_settle()
    await open_page(tester, "Scientific Calculator")

    for key in ("9", "%", "2"):
        await tester.tap(await tester.find_by_key(f"key-{key}"))
        await tester.pump_and_settle()
    assert (await tester.find_by_text("1")).count >= 1
