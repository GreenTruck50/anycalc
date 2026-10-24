The app is a flet app.
Follow PEMDAS and BODMAS rules.
There should be a conversions.yaml file that says "There should be this tab with this icon and have these conversions using these formulas."

## Unit conversions

- Load conversion groups, units, menu names, icons, descriptions, formulas, and
  directionality from `src/assets/conversions.yaml`.
- Show one Unit Conversions menu item per configured conversion group, using
  the icon specified in the YAML.
- Convert a value between units by automatically finding a route through any
  number of configured formulas in that group.
- Prefer a fully forward route. If none exists, search routes that reverse `MD`
  formulas by algebraically inverting their arithmetic operations; never
  reverse a `UD` formula.
- Report a clear error when the YAML is invalid or no valid route exists.
- Keep unit IDs referenced by conversion formulas defined in the YAML units.
- Convert live: the result and the chain update as soon as the value or either
  unit changes, so there is no Convert button.
- While the value is empty or is not a number yet (for example `-`, `3.` or
  `abc`), clear the result and the chain without reporting anything. Only a real
  failure, such as having no valid route, is shown as an error.

- Show the selected conversion form in the main content area used by the
  calculators, rather than in a popup.

## Volume and weight conversions

- Offer a "Volume Conversion" group covering metric cubic units, metric liquid
  units, metric and US culinary measures, US customary and imperial cubic and
  liquid units, US dry units, and the petroleum barrel.
- Offer a "Weight Conversion" group covering metric units, avoirdupois units,
  troy units and apothecaries' units.
- Use the legal definition of a unit as the formula factor and never a rounded
  approximation of it: 1 in = 2.54 cm (so 1 in3 = 16.387064 cm3 exactly),
  1 US liquid gal = 231 in3, 1 US dry gal = 268.8025 in3, 1 imperial gal =
  4.54609 L, 1 lb = 0.45359237 kg, 1 gr = 0.00006479891 kg, 1 dwt = 24 gr,
  1 oz t = 480 gr, 1 metric carat = 0.2 g.
- Keep every hop of a route exact whenever the true factor is a terminating
  decimal: chain derived units through exact integers (mi3 -> yd3 -> ft3 ->
  in3) instead of one long decimal factor, and give a unit an additional direct
  definition when every routed alternative would have to start with a division
  that cannot be written in decimal (the US tablespoon and teaspoon are defined
  directly in milliliters for this reason).
- Keep each decimal literal in a formula short enough to survive the engine's
  `Decimal(str(float_literal))` parsing unchanged - at most 15 significant
  digits; longer exact values must be reached by chaining integers.
- Keep every unit of a group reachable from every other unit of the same group.
- A conversion whose exact value is a terminating decimal must be displayed
  without rounding artifacts.
- Keep every decimal literal of a unit definition exact whenever the true factor
  is a terminating decimal: the inch is 25.4 mm, the mile 1609.344 m, the
  nautical mile 1852 m, the astronomical unit 149597870700 m and a light-year
  9460730472580800 m. The Length group used to route imperial units through
  rounded literals (`meter -> inch` was `x * 39.37007874`, `mile -> nautical
  mile` was `x / 1.150779448`), which made inch -> millimetre come out as
  25.4000000001…; those literals are gone.
- The only Length factor that cannot be written exactly is the parsec, which is
  648000/pi astronomical units and therefore not a rational number at all; it
  carries the most digits the engine can parse (3.2615637771674 light-years) and
  is excluded from the exactness sweep, which otherwise covers the whole group.

## Conversion chain of operations

- Below the conversion result, show the chain of operations that produced it: a
  heading "Chain of operations (N steps)" and one card per formula hop, in the
  order the hops were applied.
- Each hop card names the hop by unit name and symbol (for example
  "Centimeter (cm) → Meter (m)") and shows that hop's input and output values
  ("2500 → 25").
- The formula is not shown by default. Each hop card carries a "View formula"
  button that reveals the formula applied for that hop, and clicking it again
  collapses it.
- For a hop that reused an `MD` formula backwards, the revealed formula is the
  flipped one - additions shown as subtractions and multiplications shown as
  divisions, and vice versa - so the formula on screen is always the one that
  was actually applied. The card does not label the hop as reversed.
- The chain is not copyable.
- Converting a unit to itself shows a zero-step chain stating that the value is
  passed through unchanged, with no formula buttons.
- Changing either unit dropdown re-converts the value that is already in the
  field, so a result and a chain that do not belong together are never shown.

## Live result preview

- Both calculators show the current answer under the expression box as a small
  grey number, and it updates on every change of the expression: keypad
  presses, typed edits, values inserted from history or from a variable, and
  DEG/RAD switches.
- The preview stays hidden when there is nothing worth showing: an empty
  expression, a half-typed expression that cannot be evaluated yet, an
  expression that is already a single number, an error message, or a result that
  the display is already showing.
- Pressing `=` does not make that number disappear. It grows to the display
  size, takes the display colour, and slides up into the display box, after
  which the box holds the result.

## Calculator navigation

- Group the Regular Calculator and Scientific Calculator destinations under a
  Calculators heading in the navigation drawer, separate from Unit Conversions.
- Selecting either calculator returns the main content area to that calculator.

## Calculator keypad

- The Regular Calculator keypad puts `AC`, backspace (`⌫`), `(`, `)`, `±` and `%`
  in one utility row above the digits `0-9`, `.`, `=` and the operators `÷`, `×`,
  `−`, `+`.
- The Scientific Calculator keypad keeps those rows and adds `sin`, `cos`, `tan`,
  `√`, `log`, `ln`, `π`, `e`, `^` and the two variable buttons above them.
- A key appears on the pad exactly once: the scientific rows add only what the
  regular rows lack, so scientific mode does not show a second `(`, `)`, `%` or
  `±`, and every keypad control keeps a unique `key-<label>` id.
- Adding keys must not make the keypad taller: the regular pad stays at five rows
  (the utility keys share the top row) and the scientific pad at eight.
- The `%` key means two different things, one per pad.
- On the Regular Calculator it is the percent key of a physical calculator: on its
  own it divides by a hundred, so `50%` is `0.5`; beside `+` or `−` it takes that
  share of the number on its left, so `200+10%` is `220` and `200-10%` is `180`;
  beside `×` or `÷` it is the plain fraction, so `200*10%` is `20` and `200/10%`
  is `2000`. Chaining repeats the rule on the running total, so `200+10%+5%` is
  `231`. A `%` with nothing in front of it - pressed first, or straight after
  another operator - has nothing to take a percent of and is dropped the way a
  physical calculator ignores it, so a lone `%` evaluates to `0` and a `%` right
  after an operator leaves the expression half-entered. A postfix `%` is not
  Python syntax, so the engine rewrites the key into a marker call before parsing
  and gives that call its meaning.
- On the Scientific Calculator `%` stays the modulo operator, so `9%2` is `1` and
  `7%2.5` is `2`. The remainder keeps the sign of the dividend (`-7%2` is `-1`,
  `7%-2` is `1`) - that is the engine's `Decimal` remainder, not Python's floor
  remainder. Taking a modulo of zero reports an error.
- `±` (U+00B1, "plus-minus") is the sign-change key. It does not insert an
  operator and does not start a new entry: it flips the sign of the number the
  display rests on, which is the last number typed, or the result itself right
  after `=`. The number stays where it sits, so `5 * 3` becomes `5 * -3`, not
  `-5 * 3`.
- Pressing `±` again removes the sign instead of stacking another one, whether
  the sign was added before the number (`-5` -> `5`) or as part of a subtraction
  already underway (`5--3` -> `5-3`).
- When the expression ends on a binary operator rather than on a number, the
  number being entered next has no sign yet, so `±` writes it at the end: `5-`
  becomes `5--`, after which typing 3 gives `5 - (-3)`. A closing bracket and the
  Regular Calculator's `%` are not binary operators, so `(5+3)` and `200+10%`
  negate their last number instead; on the Scientific Calculator, where `%` is
  modulo, `9%` is an operator awaiting a number and the sign goes at the end.
- An expression with no number in it (`""`, `sin(`) is left as it is.

## Copy to clipboard

- Every result the app produces carries a small copy button (an icon-only
  `CONTENT_COPY` button, not a full-width button).
- The button copies the value as it is displayed at the moment of the click, so
  it never copies a stale value.
- Surfaces that must be copyable:
  - the calculator display (expression or result),
  - the answer of each calculation history entry,
  - the unit conversion result.
- Use Flet's clipboard service (`ft.Clipboard`), with one service instance
  shared by the whole app rather than one per button.
- Confirm each copy with a snackbar showing the copied text, truncating long
  values.
- When a surface holds nothing, report that there is nothing to copy instead of
  writing an empty string to the clipboard.
- Do not offer error text for copying: the display's copy button is disabled
  while the display shows an error message.

## Testing

- Run the suite with `flet test` (pytest flags only, no file paths - select with
  `-k`); the pure conversion-engine tests additionally run under plain `pytest`
  because they need no app host.
- Keep tests in a `tests/` folder at the workspace root, a sibling of `src/`:
  `src/` is what gets packaged into the app, test code stays on the host and
  drives the app from outside.
- Take test tooling from the `flet[test]` extra inside the optional `dev` extra
  (it provides pytest, pytest-asyncio and the screenshot-comparison libraries);
  never add it to the runtime dependency set.
- Configure pytest with `asyncio_mode = "auto"` and `testpaths = ["tests"]`; the
  `asyncio_mode` setting is required so each async test runs on the same event
  loop as the `flet_app` fixture.
- Integration tests drive the built app as a user does: a fresh app instance per
  test, controls addressed by a stable `key`, and the UI settled
  (`pump_and_settle()`) before any assertion.
- Give every control a test relies on a stable `key`: keypad buttons are keyed
  `key-<label>`, and the conversion form keys its value field, both unit
  dropdowns and the result field.
- Know the limits of the desktop test host before writing a UI test: a `key`
  only reaches ordinary controls, so drawer entries are tapped by their label
  text and a dropdown's option list cannot be opened from a test at all (unit
  switching is covered by engine tests instead); a control hidden with
  `visible = False` is still findable, so removal - not hiding - is what a test
  may assert; the host window cannot be resized from a test; and a numeric text
  field filters what a test can type, so half-typed numbers never reach it.
- Keep the conversion engine covered independently of the UI: every pair of units
  within a group must be reachable, every factor that is a terminating decimal
  must survive a conversion exact, and every chain hop the engine reports must
  re-evaluate to the input and output values shown for it.
- Keep the expression engine covered independently of the UI as well, in a second
  engine file (`tests/test_calculator_engine.py`): what the `%` key evaluates to on
  each pad, the rewrite that makes the regular pad's postfix percent parseable,
  and every `±` case the sign change can meet - including that a second press is
  the exact inverse of the first. `-k engine` selects both engine files.
- Screenshot goldens are a device feature (Android/iOS); the desktop suite
  records and compares no images.
- A conversion inaccuracy that is known and accepted is recorded as a named
  strict expected failure, naming the offending formulas, so the suite fails the
  moment the data is fixed and the marker has to be removed. The Length group's
  rounded hops were the last such failure; fixing them removed the marker, and no
  inaccuracy is currently accepted.

## Source layout

- Keep `src/main.py` as the only entry module: it builds the app and hands it to
  Flet. App behaviour must not live there.
- Split the rest of `src/` by responsibility, one concern per module:
  - `config.py` - numeric limits, display sizes, variable names and options, the
    error messages, and the path to `src/assets/conversions.yaml`;
  - `calculate.py` - the expression engine both pads sit on, including the two
    meanings of `%` and the `±` sign change;
  - `conversions.py` - the conversion configuration, route finding, formula
    application and the reported chain of hops;
  - `ui.py` - the app object: page setup, the display state (expression, result
    mode, DEG/RAD, named variables, history) and the navigation wiring;
  - `keypad.py` - which keys each pad shows and how a key looks;
  - `conversion_view.py` - the conversion form, its live re-conversion and its
    chain cards;
  - `history_view.py` - the history cards and the history drawer;
  - `variable_dialogs.py` - the Set Variable / Insert Variable dialogs;
  - `clipboard.py` - the single clipboard service behind every copy button;
  - `styles.py` - the colour palette, so one hex value cannot drift between
    controls.
- Keep the engines free of UI imports, so they stay importable - and testable -
  without an app host; view and dialog modules receive what they need
  (page, controls, callbacks) instead of reaching into an app closure.
- The two pads' keys are declared once, in `keypad.py`, and the scientific pad
  only adds its extra rows on top of the regular ones.
- Restructuring must not change behaviour: the acceptance criterion is the
  existing suite passing with the test files adjusted only for the new import
  paths.

## Packaging & entry point

- The project is configured by `pyproject.toml` at the workspace root; there is
  no `requirements.txt`. Runtime dependencies are `flet[cli,desktop]` (the
  desktop client and the `flet` command are declared, never pip-installed at
  first launch) and `PyYAML`; test tooling belongs in the optional `dev` extra,
  not in the runtime set.
- The app's entry point is `src/main.py`, declared to Flet with
  `[tool.flet.app] path = "src"` and `module = "main"`. There is no console
  script: the app is started with `flet run` (from the workspace root) or run
  from a packaged artifact, and `pyproject.toml` deliberately installs no
  Python package (`[tool.setuptools] packages = []`, `py-modules = []`) so a
  `pip install` only resolves the dependencies.
- The app only starts when that module is executed as `__main__`; importing it
  (e.g. from tests) must not open a window.
- The app targets desktop **and** mobile. The same `src/` is packaged with
  `flet build linux|macos|windows` (desktop), `flet build apk|aab` (Android
  `.apk` / Play Store `.aab`), `flet build ipa|ios-simulator` (iOS - needs a
  macOS host with Xcode) and `flet build web`. Every target is run from the
  workspace root - not from `src/`.
- The artifact must contain the app, `src/assets/conversions.yaml` and the
  declared dependencies. `org` and `product` in `[tool.flet]` are what become the
  application/bundle id (`com.github.greentruck50.anycalc`) and the name the platform shows.
- Keep `src/` platform-neutral: no module may branch on the running platform or
  import a desktop-only package. The only platform-specific calls are the window
  size and minimum size set on the page in `ui.py`, which a mobile build ignores.
- `src/` is an *import root*, not a Python package - the stock Flet convention.
  Flet packages the contents of the app folder as the artifact's import root, so
  inside the artifact the modules sit side by side as top-level modules
  (`main.py`, `ui.py`, `styles.py`, `assets/conversions.yaml`).
- Therefore every module of the app imports its siblings by bare name
  (`from ui import AnycalcApp`, `from config import ...`, `import calculate`).
  No module may use a `src.`-prefixed import, there is no `src/__init__.py`, and
  no module contains import-path fix-up code - the same import works in the
  workspace, in the tests and inside the artifact.
- The host is given that same root by `pythonpath = ["src"]` under
  `[tool.pytest.ini_options]`; an editor needs the equivalent
  `python.analysis.extraPaths` setting, which lives in that machine's own editor
  settings - `.vscode/` is not tracked in this repository.
- Only sources and project configuration are tracked. Everything a build or a
  test run regenerates (`build/`, the Python/pytest/Dart caches) stays ignored,
  along with each machine's own Python environment and editor settings.

