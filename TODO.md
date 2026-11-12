If you are an AI agent DON'T do anything in here unless told!
Every item ends with its number in parentheses so it can be referred to by number. This is TODO.md

- [ ] Add new section for other calculators (1)
- [ ] Add a compost calculator like https://urbanwormcompany.com/composting-calculator-carbon-nitrogen-ratio/ (2)
- [ ] Add a gear ratio calculator (3)
- [ ] Add a regular ratio calculator (4)
- [ ] Add a plant orbit calculator (2 bodies) (5)
- [ ] Add a credits/about section in the settings (6)
- [ ] Add a precision box to the settings menu (7)
- [ ] Change the app logo because it's trash (8)

## New calculators

- [ ] Percent pack: %, % of, % change, reverse %, tip, markup - the keys people look for first (9)
- [ ] Date & time calculator: days between dates, add/subtract, age, duration between two times (10)
- [ ] Speed / distance / time solver (11)
- [ ] Fuel economy: L/100 km <-> mpg <-> km/L (reciprocal scale - good stress test for the engine) (12)
- [ ] Number bases: hex / octal / binary <-> decimal, plus roman numerals (13)
- [ ] Fraction mode: exact rationals, simplify, mixed numbers (the engine is Decimal today) (14)
- [ ] Prime factorisation + divisor list + primality check (15)
- [ ] Aspect-ratio calculator (diagonal vs 16:9 / 21:9 / 4:3) (16)
- [ ] Engineering pack next to the gear calculator: belt/pulley RPM, compound gear train, mechanical advantage, module vs circular pitch, AWG <-> mm2 wire gauge, TPI <-> thread pitch (17)
- [ ] Compost calculator, expanded: several feedstock inputs -> solve the blend that hits a target C:N, with moisture as a second constraint (18)
- [ ] Plant-orbit calculator, defined: semi-major axis + two masses -> period (Kepler III), vis-viva speed at r, and a small 2-body diagram (19)

## Keypad & memory

- [x] MRC / M+ / M- (memory) buttons on the regular pad, plus a setting to have them on the scientific pad too (20)

## Settings - extends item 7

- [x] Precision box: decimal places, rounding mode (half-up / half-even / truncate) (21)
- [ ] Number formatting: thousands separator style (comma / space / none) (22)
- [ ] Default angle mode persisted in app state (deg / rad / grad is per-session today) (23)
- [x] "Follow system theme" option - styles.THEMES is a fixed tuple with no auto mode (24)
- [ ] Add more themes (25)
- [x] History length setting (max 100) + "Clear history" + "Reset all app data" (with prompt for confirmation) in Settings (26)
- [ ] Accessibility: font scale and a large-keypad layout for phones (27)

## Credits / about - extends item 6

- [ ] About section: version read from pyproject.toml (nothing in src/ reads version today), license, repo + docs links, third-party credits (Flet, Flutter, Material icons) (28)

## Data & persistence

- [ ] Export / import app data as JSON (theme, colors, history, saved pi) - file picker on desktop, share sheet on mobile (29)
- [ ] Persist named variables across restarts - saved state carries history but not variables (30)
- [x] Restore the last-used unit pair and currency pair on launch (31)
  - Done 2026-11-11. Each conversion page keeps its own pair and the currency page
    keeps its pair; both go into the saved app state and are re-applied when the
    page opens. A pair naming a unit the YAML no longer has - or a currency the API
    no longer offers - falls back to that page's built-in default pair, and "Reset
    all app data" forgets them. Spec: `calculator_spec.md` (Unit conversions,
    Currency conversion, Saved app data); tests: `tests/test_remembered_pairs.py`,
    `tests/test_data_storage.py`, `tests/test_currency_view.py` and one app-host
    test in `tests/test_app.py`.
- [ ] Favourite / pinned unit pairs at the top of the conversions menu (32)

## Conversions & currency

- [ ] Search / filter box over the unit menu - conversions.yaml is 2778 lines of units, scrolling is losing (33)
  - User choice: set enable_filter to true on all dropdown boxes in the app
  - Researched 2026-11-10, not implemented. The menu is a plain `ft.Dropdown`, and
    Flet 1.1.2 already ships the filter - no app-side option-list juggling needed:
    `ft.Dropdown(enable_filter=True, editable=True)`, the recipe in Flet's own
    `examples/controls/material/dropdown/icon_selection` (which also puts a
    `leading_icon=ft.Icons.SEARCH` on the field).
  - How it works: Flet's client (`packages/flet/lib/src/controls/dropdown.dart`)
    passes both flags straight to Flutter's `DropdownMenu`. The default filter is
    `entry.label.toLowerCase().contains(typed.toLowerCase())` - case-insensitive
    substring on the option's **label**, which for this app is the option `text`,
    i.e. `"Mile per hour (mph)"`: name *and* symbol are searchable, and the query is
    matched as plain text, never as a regex. `enable_search` (already on by default)
    highlights and scrolls to the first match; with filtering on it is redundant but
    harmless. Flutter's `filterCallback` / `searchCallback` are not exposed by Flet,
    so the predicate cannot be customised.
  - `editable=True` is not optional: the Dart maps it to `_focusNode.canRequestFocus`
    and Flutter renders the field `readOnly` whenever it cannot take focus, so with
    the default `editable=False` there is nothing to type and `enable_filter` does
    nothing at all.
  - The one real cost: an editable field can be left holding text that is not any
    option, while the Python `value` still names the old unit - the Dart rewrites the
    field text only when the Python `value` *changes*. `on_text_change` reports the
    typed text (`e.control.text`); `on_select` fires only for a real pick. So the
    form needs a blur/submit rule: match the typed text against the option labels,
    select it when exactly one option matches, and otherwise put the old selection
    back (force it by setting `value` to `None` and back, since an unchanged value
    never rewrites the text). The live re-conversion handler stays on `on_select`
    exactly as it is now.
  - Untested against the app's layout: the unit dropdowns are wrapped in a `Row` with
    `expand=True` to make them as wide as the value field (see the comment in
    `conversion_view.py`); `editable` should not disturb that, but it has to be
    checked on desktop and on the emulator. `flet test` cannot reach a `Dropdown`'s
    options at all (see the header notes of `tests/test_app.py`), so coverage for
    this is a stub-page assertion that the flags are set, plus a manual look.
  - Alternative if the built-in filter misbehaves: an app-side "Filter units" field
    above the two dropdowns that rebuilds `options` with the matching subset. Costs a
    full `DropdownMenu` rebuild per keystroke - the Dart hashes the option set into
    the widget key to recompute the menu's intrinsic width - which closes an open
    menu, and duplicates logic Flutter already has.
  - Separate menu, same complaint possible later: the drawer's conversion list is 15
    entries now that (34) has landed. It is short enough to scroll, and Flet 1.1.2 has
    `ft.SearchBar` if it ever is not.
- [x] Missing unit groups: speed, pressure, power, angle, data rate, mass flow (34)
- [ ] Custom user-defined units / formulas stored alongside conversions.yaml (35)
- [x] Validator / test that walks the whole formula graph in conversions.yaml and proves every unit in a group is reachable from every other (MD reversal is silent when it fails) (36)
  - Already in place, and it now covers all fifteen groups because (34) landed. In
    `tests/test_conversion_engine.py`: `test_every_pair_of_units_is_reachable`
    parametrizes over every conversion entry and asserts `find_conversion_path`
    finds a route for all n² ordered pairs of that group's units, and
    `test_group_has_exactly_its_own_units` asserts every formula endpoint is one of
    the group's own units and that no unit is left unwired. The "MD reversal is
    silent" half is covered by the loader itself: `load_conversion_config()`
    evaluates each `MD` formula forward and then reverses it
    (`src/conversions.py:104-108`), so an irreversible formula raises as soon as the
    config is read - which every test in that file does.
- [ ] Currency: staleness badge + "rates as of ..." line + offline last-known-rates fallback (37)

## Pi page

- [x] Digit search: find a digit string in the computed digits and report its position (38)
- [ ] Save the digits to a text file; copy in chunks for 100 000 000 digits (39)
- [ ] Pause / resume a long computation; ETA next to the progress bar (40)

## Repo & quality

- [ ] CI that runs the tests: .github/workflows has only codeql.yml and docs.yml - no workflow runs pytest / flet test on a PR (41)
- [ ] Release checklist + tag flow; keep the version in pyproject.toml as the only source (42)
- [ ] Dependabot / pip-audit for flet + PyYAML (43)
- [ ] Issue + PR templates and a label taxonomy (.github/ISSUE_TEMPLATE does not exist) (44)
- [ ] README screenshots per theme + a short pi GIF; mkdocs.yml has no search plugin and a 5-item nav over 5 large docs pages (45)
- [ ] ruff + pyright/mypy strict + pre-commit as dev extras (46)

## Desktop input

- [x] Physical keyboard on desktop: no on_keyboard_event anywhere in src/ - wire digits, operators, Enter (=), Backspace, Esc (clear) and history navigation (47)

## Scratch
- [ ] (blank) (48)