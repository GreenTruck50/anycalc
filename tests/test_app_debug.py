"""Temporary probe: what the built settings dialog exposes as text."""

import flet.testing as ftt


async def test_debug_caption(flet_app: ftt.FletTestApp) -> None:
    tester = flet_app.tester
    await tester.pump_and_settle()

    async def probe(stage: str) -> None:
        for _ in range(4):
            await tester.pump_and_settle()
        caption = (await tester.find_by_text("Custom color: #4F7DFF")).count
        any_caption = (await tester.find_by_text_containing("Custom color:")).count
        entry = (await tester.find_by_text("Custom color")).count
        blue = (await tester.find_by_text("Blue")).count
        green = (await tester.find_by_text("Forest green")).count
        probes = {}
        for candidate in (
            "PROBE",
            "PROBE 'custom'",
            "PROBE '#4F7DFF'",
            "PROBE None",
        ):
            probes[candidate] = (
                await tester.find_by_text_containing(candidate)
            ).count
        print(
            f"DEBUG {stage}: caption={caption} any_caption={any_caption}"
            f" entry={entry} blue={blue} forest={green} probes={probes}"
        )

    await tester.tap(await tester.find_by_key("settings-button"))
    await tester.pump_and_settle()
    await tester.tap(await tester.find_by_key("settings-reset"))
    await tester.pump_and_settle()
    await probe("BUILT-IN THEME")

    await tester.tap(await tester.find_by_key("settings-theme-dropdown"))
    await tester.pump_and_settle()
    await tester.tap((await tester.find_by_text("Custom")).last)
    await tester.pump_and_settle()
    await probe("CUSTOM THEME")

    await tester.tap(await tester.find_by_key("settings-primary-color"))
    await tester.pump_and_settle()
    await probe("COLOR MENU OPEN")

    await tester.tap((await tester.find_by_text("Custom color")).last)
    await tester.pump_and_settle()
    await probe("AFTER CUSTOM ENTRY TAP")

    assert (await tester.find_by_key("settings-close")).count == 1
