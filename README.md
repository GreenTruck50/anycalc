# anycalc

Calculate anything — a Flet calculator for desktop and mobile: expressions,
scientific mode, named variables, history, live unit conversions and a π it
computes for itself.

## Layout

```
pyproject.toml            project metadata, dependencies, Flet build config
src/                      the app (entry point: src/main.py)
  main.py                 starts the app — it holds no behaviour of its own
  ui.py                   AnycalcApp: page setup, display state, keypad wiring,
                          drawer navigation
  calculate.py            the expression engine both pads sit on (Decimal math,
                          the two meanings of %, the ± sign change)
  conversions.py          the unit conversion engine (YAML config, route finding,
                          formula application, the chain of hops)
  pi.py                   the pi computation (Chudnovsky + binary splitting) and
                          the one pi the program calculates with
  pi_value.py             a pi run packaged for the page — timing, progress
                          numbers, adopting a finished run
  config.py               numeric limits, display sizes, variable names/options,
                          error messages, the path to the unit data
  styles.py               the colour palette
  clipboard.py            the one clipboard service behind every copy button
  keypad.py               which keys each pad shows and how a key looks
  conversion_view.py      the live conversion form and its chain cards
  pi_view.py              the pi page — digit choice, progress card, "use this
                          value", the lazy digits dialog
  history_view.py         history cards and the history drawer
  variable_dialogs.py     the Set / Insert Variable dialogs
  assets/conversions.yaml unit groups and the formulas between them
tests/                    the test suite — host-side; src/ is what gets packaged
```

## Unit conversions

`src/assets/conversions.yaml` defines the groups (Length, Time, Temperature,
Data, Volume, Area, Weight, Energy, Force), their units and the formula between
each pair of units. The factors are the legal definitions themselves -
1 lb = 0.45359237 kg, 1 grain = 0.00006479891 kg, 1 US gal = 231 in³,
1 imperial gal = 4.54609 L, 1 in³ = 16.387064 cm³, 1 in = 25.4 mm,
1 nautical mile = 1852 m, 1 cal (IT) = 4.1868 J, 1 Btu (IT) = 1055.05585262 J,
1 kWh = 3.6 MJ, 1 kgf = 9.80665 N, 1 lbf = 4.4482216152605 N - so results stay
exact as far as `Decimal` allows. The only hops that cannot be written exactly
are the parsec (648000/π astronomical units) and the thermochemical Btu (its 5/9
never ends as a decimal). The rules a new unit has to follow are in the
"Volume and weight conversions" and "Energy and force conversions" sections of
`calculator_spec.md`.

## Pi calculation

The app computes its own π — an expression's `pi` is never `math.pi`. On
start-up it computes 12 decimals and every calculation, both pads included,
multiplies by that value; the Pi Calculation page (under "Other" in the drawer)
computes any count from 3 to 100 000 000 decimals with Chudnovsky + binary
splitting, shows a progress bar with a speed and time estimate, and offers "Use
this value for the program" to make a finished run the π everything uses. Viewing
the digits opens a dialog that fills in more lines as you scroll, so a hundred
million decimals are never put on screen at once.

π is computed on plain Python integers by default. `gmpy2` — in the optional
`[pi]` extra, and already in `[dev]` — makes big runs far faster; it is a C
extension with no Android wheel, so it is deliberately *not* a runtime
dependency and `src/pi.py` falls back to the stdlib when it is missing.

## Setup

The project needs Python 3.11+. Install its dependencies:

```bash
pip install -e .                # add ".[dev]" for the test tooling
```

## Run

```bash
flet run                        # or: python src/main.py
```

`src/` is Flet's import root, not a package: the modules import each other by
bare name (`from ui import AnycalcApp`), which is exactly how the packaged app
sees them.

## Tests

```bash
flet test                # everything; provisions a test host, then runs pytest
flet test -k engine      # the *_engine.py files only, no Flutter host
flet test -k app         # the Flet UI tests only
```

`flet test` takes pytest flags, not file paths (select with `-k`); flags after
`--` are passed to pytest verbatim. The pure-logic tests can also be run without
Flet at all: `python -m pytest -k engine`, plus `python -m pytest
tests/test_pi_view.py` (that one drives the pi page against a stub page, so it
needs no window either).

Two layers live in `tests/` (a sibling of `src/`, which is what gets packaged
into the app):

- `test_conversion_engine.py` — unit tests that import `conversions` and hammer the
  conversion engine: every pair of units in every group must be reachable, every
  terminating factor must stay exact, and every chain hop the engine reports has
  to re-evaluate to the value it prints.
- `test_calculator_engine.py` — unit tests for the expression engine behind the
  two calculators: the regular pad's `%` as a desk-calculator percent (`200+10%`
  is `220`, `50%` is `0.5`, `200*10%` is `20`), the scientific pad's `%` as
  modulo (`9%2` is `1`), and the `±` sign change, including the whole
  sign-change table and the fact that pressing `±` twice is a no-op.
- `test_pi_engine.py` — unit tests for the π computation: the digit count of a
  run, 100 000 and 500 000 decimals held against MPFR's own π (`gmpy2.const_pi`),
  the progress numbers, stopping a run, the offered range and the one π the
  program calculates with.
- `test_pi_view.py` — the pi page without a window: the digit-count rules,
  adopting a finished run, and the lazy digits dialog (how many lines exist
  before any scrolling and how scrolling grows them).
- `test_app.py` — Flet integration tests. `flet test` packages `src/` into a
  monolithic app with an embedded Python and the test drives *that* (drawer
  navigation, the conversion page re-converting as you type, the keypad) through
  `flet.testing`.

`flet[test]` in the `dev` extra brings pytest, pytest-asyncio and the screenshot
libraries; `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` is required
by the `flet_app` fixture. The first run downloads the Flutter SDK and builds a
test host (slow, and it leaves a ~1 GB `build/` directory behind); later runs are
cached. Screenshot goldens are Android/iOS only — the desktop suite compares no
images.

## Build packages — desktop & mobile

The same `src/` ships to desktop and to phone. Run from the workspace root —
`[tool.flet.app]` in `pyproject.toml` points Flet at `src/main.py`, so no
`cd src` is needed:

```bash
flet build linux           # desktop bundle -> build/linux/
flet build apk             # Android .apk
flet build aab             # Android .aab (Play Store)
flet build ipa             # iOS - needs macOS with Xcode
flet build web             # static web bundle
```

Desktop: the artifact is the relocatable bundle `build/linux/` (executable
`anycalc`, `app/`, `site-packages/`, `python3.14/`, `data/`, `share/`); pass
`-o <dir>` to put it somewhere else.

Mobile: `apk` / `aab` go through the Flutter SDK and need an Android SDK plus a
JDK (here: `~/Android/Sdk`, `java`, `adb` on PATH); `ipa` builds only on macOS
with Xcode. `org` / `product` in `[tool.flet]` set the application id and the
app label, and `src/` contains no platform-specific code — every target packages
the same source.

Every target needs the Flutter SDK at the version Flet pins (managed copy in
`~/flutter/<version>`); `flet build` installs it there on demand. Of the targets
above, only the Linux one has been built from this workspace so far.

Note: once a build exists, `flet run` / `python src/main.py` reuse the built
client at `build/linux/anycalc` instead of the normal desktop client — move or
delete `build/linux` (or the whole `build/` dir) to go back.


