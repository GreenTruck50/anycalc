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
  entries have to be tapped by their label text, and switching the From/To unit
  cannot be driven from a UI test at all, so the unit pairs are covered instead
  by the exhaustive route tests in ``tests/test_conversion_engine.py``.
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
"""

import flet.testing as ftt

from conversions import load_conversion_config

UNIT_GROUPS, _ = load_conversion_config()
UNIT_LABELS = {
    unit["id"]: f"{unit['name']} ({unit['symbol']})"
    for group in UNIT_GROUPS
    for unit in group["units"]
}


def hop_line(source_id: str, target_id: str, index: int = 1) -> str:
    """The heading a chain card prints for one hop."""

    return f"{index}. {UNIT_LABELS[source_id]} → {UNIT_LABELS[target_id]}"


async def open_page(tester: ftt.Tester, label: str) -> None:
    """Open the drawer and select the entry with this label."""

    await tester.tap(await tester.find_by_key("menu-button"))
    await tester.pump_and_settle()
    destination = await tester.find_by_text(label)
    assert destination.count == 1, f"{label!r} is not in the drawer"
    await tester.tap(destination.first)
    await tester.pump_and_settle()


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


async def test_drawer_switches_to_the_scientific_calculator(
    flet_app: ftt.FletTestApp,
) -> None:
    """The drawer is the only navigation, and it rebuilds the keypad."""

    tester = flet_app.tester
    await tester.pump_and_settle()

    assert (await tester.find_by_key("key-7")).count == 1
    assert (await tester.find_by_key("key-sin")).count == 0

    await open_page(tester, "Scientific Calculator")

    assert (await tester.find_by_key("key-sin")).count == 1
    assert (await tester.find_by_key("key-Set Variable")).count == 1
    assert (await tester.find_by_key("key-±")).count == 1
    assert (await tester.find_by_text("SCIENTIFIC MODE")).count == 1
    # the regular rows stay, so the digits are still there
    assert (await tester.find_by_key("key-7")).count == 1


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
