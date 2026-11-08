Running log entry and reference for the test suite added 2026-10-24.

## 2026-10-24 — `%` is a real percent key on the regular pad; the Length xfail is gone

*   `tests/test_calculator_engine.py` grew from 56 to **96** tests and the `%` block is split by pad. Regular pad (percent): `50%` → 0.5, `200+10%` → 220, `200-10%` → 180, `200*10%` → 20, `200/10%` → 2000, chaining on the running total (`200+10%+5%` → 231), and a `%` with nothing in front of it being dropped by the rewrite, so a lone `%` still evaluates to 0 rather than erroring (`5+%` is what errors: the rewrite leaves `5+`, so `=` reports "Invalid expression"). Scientific pad (modulo): unchanged — `9%2` → 1, `7%2.5` → 2, `-7%2` → -1, `5%0` → "Invalid result". The rewrite that makes a postfix `%` parseable (`apply_percent_operators`: `200+10%` → `200+_percent(10)`, also wrapping a closing bracket like `sqrt(4)%` or a name like `pi%`) is tested directly, as is `is_percent_call`.
*   `tests/test_conversion_engine.py` (75 → **82** tests): the `LENGTH_DRIFT` data and its `xfail(strict=True)` marker are **deleted**. The exactness sweep no longer exempts the Length group — every terminating-decimal pair in it must come out bit-for-bit. The parsec is excluded by name, with the reason in a comment: a parsec is 648000/π astronomical units, so its factor is not a rational number and no literal can be exact.
*   `tests/test_app.py` (6 → **7** UI tests): `test_regular_calculator_percent_key_and_sign_change` types `200+10%` on the regular pad and asserts the live answer preview reads `220` (percent, not modulo), then checks `5%` → 0.05 and the `±` behaviour; `test_scientific_calculator_percent_key_is_modulo` pins `9%2` → `1`, so both meanings of the same key are covered through the real UI.
*   **Full suite verified 2026-10-24:** `**flet test**` **→ 185 passed in 339 s** (7 UI + 96 calculator engine + 82 conversion engine), no xfail, no skips. Engine only: `.venv/bin/python -m pytest -k engine` → 178 passed in ~3 s.

## 2026-10-24 — pytest + `flet test` suite added (conversion engine + UI)

*   `pyproject.toml`: the `dev` extra now installs `flet[test]>=1.0.4` (pulls in `pytest`, `pytest-asyncio` and the screenshot libraries) plus explicit `pytest` / `pytest-asyncio` pins; added `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and `testpaths = ["tests"]`. Runtime dependencies unchanged.
*   New `tests/conftest.py` — puts the repo root on `sys.path` so both kinds of tests can `import src.main` (safe since the app only runs under `__main__`).
*   New `tests/test_conversion_engine.py` — pure-python tests, no app host: every unit pair inside a group is reachable, every terminating-decimal pair stays bit-exact, chain hops re-evaluate to the values printed (`_evaluate_conversion_formula` is re-run per hop), formula-flip, same-unit pass-through and cross-group errors are pinned, plus ~40 published reference values (NIST/legal) and a 37-digit cubic-mile precision check.
*   New `tests/test_app.py` — Flet integration tests through `flet.testing`: drawer navigation to Scientific Calculator and to conversion pages, the conversion page converting live as the value changes, clearing the value clearing result + chain quietly, keypad arithmetic and `=` flipping EXPRESSION → RESULT.
*   At the time the Length group still used rounded literals (`meter -> inch` was `x * 39.37007874`, `mile -> nautical mile` `x / 1.150779448`), which was encoded as `xfail(strict=True)` naming the offending formulas. _Superseded the same day: the exact anchors (inch = 25.4 mm, mile = 1609.344 m, nautical mile = 1852 m, light-year = 9460730472580800 m) are now in the YAML and the marker is removed — see the entry above._
*   Docs: `README.md` gained a "Tests" section, `calculator_spec.md` gained a "Testing" section (what belongs in engine tests vs UI tests, key conventions, the tester limits below), and the `pyproject.toml` header comment documents the test command.

## 2026-10-24 — keypad keys `%` (regular pad) and `±` (both pads)

*   New `tests/test_calculator_engine.py` — pure-python tests for the expression engine rather than the conversion graph: what the `%` key evaluates to and the 21-case `±` sign-change table, each case also asserted to be its own inverse. Named `…_engine.py` on purpose so `-k engine` picks it up together with `test_conversion_engine.py`. _The_ `_%_` _half of that file was rewritten the same day when_ `_%_` _stopped being modulo on the regular pad._
*   `tests/test_app.py` gained `test_regular_calculator_percent_key_and_sign_change` (taps `key-%` and `key-±` on the regular pad and reads the live answer preview), and the drawer test now also asserts `key-±` exists after switching to Scientific.
*   Tester gotcha worth remembering: **a keypad key that exists in both the scientific rows and the regular rows is found twice**, because scientific mode renders the regular rows underneath its own — `find_by_key("key-±")` returned count 2 (the pad already had this problem with `(` and `)`). The app now keeps every key on the pad exactly once, so `key-<label>` stays unique and a UI test can assert `count == 1` again.

## How to run

```
.venv/bin/flet test                 # everything (185 tests, ~5½ min)
.venv/bin/flet test -k engine       # both engine test files, ~3 s, no Flutter host
.venv/bin/flet test -k app          # the 7 UI tests, ~4-6 min (~35-60 s per test)
```

`flet test` must run from the workspace root (it reads `pyproject.toml`, and `[tool.flet.app]` points it at `src/main.py`). It accepts pytest flags only — positional test paths are rejected with a usage error, so select with `-k` (`-k percent_key` runs the two percent UI tests plus the matching engine ones); anything after `--` goes to pytest verbatim (`-- -s` for print output). The pure tests also run under plain `.venv/bin/python -m pytest -k engine`. `flet test` needs a display for the app hosts it boots (`WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000`). The first UI run provisions/builds the Flutter test harness; later runs reuse it, but every UI test still boots a fresh app host — that host boot, not the assertions, is what makes the suite slow. `flet test` leaves a `build/` tree behind (`flutter`, `python-app`, `site-packages`).

## Flet 1.0.5 tester limits — learned the hard way, read before writing a UI test

Everything below still applies on Flet 1.1.2 except the two `Dropdown` rules that the 2026-11-07 section at the end of this page replaces: which menu-row index a test can tap, and what has to be named in `page.update(...)` for a revealed control to repaint.

*   `key` only reaches ordinary controls. Keypad buttons (`key-7`, `key-sin`) and the conversion form (`conversion-value`, `conversion-result`) are found by key, but `NavigationDrawerDestination` and `Dropdown` options never are. Drawer entries must be tapped by **label text** (`find_by_text("Volume Conversion")`), and switching the From/To unit cannot be driven from a UI test at all — unit pairs are covered by the exhaustive engine tests instead.
*   **A** `**Finder**` **has no** `**.value**` (and there is no `tester.get`): `(await tester.find_by_key("display")).first.value` raises `AttributeError: 'Finder' object has no attribute 'value'`, which is how the percent keypad test failed on its first run. Assertions can only be about which texts/keys are findable, so a keypad test asserts the **live answer preview** (a plain `Text` under the display box) and proves `=` committed by the caption flipping `EXPRESSION` → `RESULT`. The same is why the conversion tests read the chain cards rather than the read-only Result field.
*   A key must be unique on screen: duplicated keypad keys come back as `count=2` and make `count == 1` assertions fail.
*   A control hidden with `visible=False` stays in the finder tree. "The chain disappeared" has to be asserted on the hop texts the app actually removes, never on the "Chain of operations" header, which is only hidden. (A `find_by_key("conversion-chain")` on the empty chain `Column` also returns 0, so keys are not an alternative here.)
*   `flet_app.resize_page()` raises `RuntimeError('page is not initialized')` — a test cannot choose its window size; the default desktop window fits these pages.
*   The Value field is a `KeyboardType.NUMBER` field, and the tester's `enter_text` respects that filter: typing `"3."` arrives as `"3"`. So a half-typed number never reaches the app from a test; clearing the field (empty string) is the UI path into the app's "quietly clear result and chain" branch, while the parse-failure branch (`"abc"`) is unreachable from a desktop test and deliberately untested.
*   `flet_app.tester.enter_text(finder, text)` **replaces** the field content (it does not append), and awaiting a finder twice reuses a dead coroutine — hold the finder in a variable if it is needed more than once.
*   Screenshot goldens are Android/iOS only, so this desktop app has none.

## Follow-ups

*   ~~Fix the Length group's rounded literals in~~ `~~src/assets/conversions.yaml~~` — done 2026-10-24; `LENGTH_DRIFT` and its marker are deleted.
*   ~~Decide whether~~ `~~%~~` ~~is percent-of or modulo~~ — settled 2026-10-24 per pad: percent on the Regular Calculator (desk-calculator semantics), modulo on the Scientific Calculator. Any change to that split has to move `test_calculator_engine.py`'s two `%` blocks and the two UI assertions together.
*   Consider whether the drawer/dropdowns should be sorted (see the hub note's ordering item) — sorting would also make UI tests that address drawer entries by index safe.
*   The UI suite's cost is 7 app-host boots (~5 min). If it gets extended, keep new coverage in the engine files and only add UI tests for wiring the engine cannot see.

## 2026-10-26 — two testing paths: host by default, Android emulator only on request

`AGENTS.md` and `calculator_spec.md` (Testing) now say this explicitly, because the spec used to read as if on-device testing were the normal route.

**Host path — the default for every change**

*   `flet run` to look at the app, `flet test` for the whole suite, `flet test -k engine` for the two engine files (178 tests ≈ 3 s, cheap enough to run constantly).
*   Budget the full suite ≈ 6 min (185 tests, 339 s measured 2026-10-24). A `flet test` that runs for minutes is working, not hung — a 150/300 s timeout is simply too short, which is what made the full suite look stuck on 2026-10-26.
*   No emulator, device or APK is involved, and this path alone judges a change.

**Android emulator path — only when testing on Android is asked for**

*   Order of work: `./build.sh apk` (or `./build.sh apk --debug` for a debuggable install — that artifact is `build/apk/app-debug.apk`, not the `anycalc.apk` the script below looks for) → if the AVD is not running, prove KVM (`~/Android/Sdk/emulator/emulator-check accel` → `KVM (version 12) is installed and usable`; never grep the launch line, emulator 37 puts only `-avd <name>` in argv) → boot normally (`-no-audio -no-boot-anim`) → `adb install -r build/apk/anycalc.apk` → `adb shell am start -n com.github.greentruck50.anycalc/.MainActivity` → drive/read with `adb`.
*   `./test-with-emulator.sh anycalc` builds first, then runs that sequence for the `anycalc` AVD, reusing it if already running or starting it with its normal boot behavior. Pass another AVD name to select a different device; `ANDROID_SDK_ROOT` or `ANDROID_HOME` can override the default SDK directory.
*   Cost: `flet build apk` ≈ 8 min cold, dominated by Gradle. The Gradle + Kotlin compile daemons and `~/.gradle` (4.2 GB) stay alive between runs — leave them up, a rebuild is then minutes.
*   Transient effects (ripple, animation, in-between frame): hold instead of tap — `adb shell input motionevent DOWN x y`, `adb exec-out screencap -p > /tmp/press.png`, `adb shell input motionevent UP x y`. One capture proves both the visual effect and that the press committed. `screencap` pixels map 1:1 to `adb shell input` coordinates (`adb shell wm size` = 1080x2400 here).
*   This is the only route for a visual check of the _running_ app: nothing injects synthetic input into the real desktop window from Wayland (xdotool is both absent and unable), and a host screenshot only catches whatever frame is up plus the host's own windows. Ask before taking a device run for that.

## 2026-11-07 — Flet 1.1.2 moved the Dropdown renderer; two rules above changed

The 1.0.5 rules mostly still hold (`Finder` is still `{id, count, index}` with `.first` / `.last` / `.at(i)` and no `.control` / `.value` — `flet/testing/finder.py`; `find_by_text` is still exact-match, `find_by_text_containing` takes a regex), but `Dropdown` is a different widget now: `flet-1.0.5/lib/src/controls/dropdown.dart` builds on `flutter/material.dart`, `flet-1.1.2/.../dropdown.dart` imports `package:material_ui` and builds a Material 3 `DropdownMenu` with `DropdownMenuEntry`s. Measured with a throwaway probe against the settings dialog:

*   **The tappable menu row is no longer `.last`.** With the "Custom color" entry offered by two closed dropdowns and one open menu, `find_by_text("Custom color")` returns 3 matches and the menu row is **index 1** — right after the open dropdown's own offstage copy. `.at(0)` only dismisses the menu; `.last` belongs to the other dropdown's offstage copy and its tap lands on whichever menu row is under that coordinate. The finder includes entries outside the menu's visible viewport, though, so the picker entry at the top is not tappable when the menu opens on the default Blue selection. `test_settings_applies_as_it_is_picked_and_resets_to_defaults` drives a visible named-color selection instead; the settings unit tests cover the picker reveal.
*   **The whole option list paints once the menu is open** — all 32 palette entries were findable — so the 1.0.5 limit "a long list paints only the items around the selected one" is gone. Findable does not mean tappable: entries outside the viewport still cannot be driven with the host tester. Option texts are also findable while a dropdown is closed (one copy per dropdown offering it, plus one for what it displays), which is what the settings test's counting relies on.
*   **A setting revealed *inside* an already visible group does not repaint on a `visible` flip at all.** Tapping "Custom color" selects it — a probe proved the handler ran, `picker.visible`/caption `visible` were `True`, the caption text was right and `page.update(...)` returned without raising — yet the caption Text stayed unfound. Naming the dialog's content `Column` (`settings_content`), the group's own `Column` and the leaf controls in the update changed nothing, and neither did doing the reveal before the full `page.update()` inside `apply_theme`. What does paint is a **child-list change**: `src/ui.py::_sync_color_visibility` now adds the caption and the picker to the group's `Column` (and takes them out again) instead of hiding them. A whole group hidden by a `visible` flag still works, because a theme switch repaints the page anyway.
*   Reopening the settings dialog rebuilds it from stored state, and the "Custom color" entry is a *mode*, not a stored color: if the color on screen is a palette color, the rebuilt dialog opens on that named entry instead of "Custom color". So a UI test must not assume the mode survives a close/reopen.
*   Cost of one targeted UI run with a changed `src/` (app host repackaged, harness cached): 60–70 s for a single probe test. `flet test -k "app or settings"` (29 tests, 11 min) is still the expensive one.

*   Used on 2026-10-26 to verify the keypad ripple (see the change-log note): held-press captures showed the white ripple spreading through `8`, `9`, `=` while the press still committed.