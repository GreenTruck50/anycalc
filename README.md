# anycalc

Calculate anything — a Flet desktop calculator: expressions, scientific mode,
named variables, history and live unit conversions.

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
  config.py               numeric limits, display sizes, variable names/options,
                          error messages, the path to the unit data
  styles.py               the colour palette
  clipboard.py            the one clipboard service behind every copy button
  keypad.py               which keys each pad shows and how a key looks
  conversion_view.py      the live conversion form and its chain cards
  history_view.py         history cards and the history drawer
  variable_dialogs.py     the Set / Insert Variable dialogs
  assets/conversions.yaml unit groups and the formulas between them
tests/                    the test suite — host-side; src/ is what gets packaged
```

## Unit conversions

`src/assets/conversions.yaml` defines the groups (Length, Time, Temperature,
Data, Volume, Weight), their units and the formula between each pair of units.
The factors are the legal definitions themselves - 1 lb = 0.45359237 kg,
1 grain = 0.00006479891 kg, 1 US gal = 231 in³, 1 imperial gal = 4.54609 L,
1 in³ = 16.387064 cm³, 1 in = 25.4 mm, 1 nautical mile = 1852 m - so results
stay exact as far as `Decimal` allows. The only hop that cannot be written
exactly is the parsec (648000/π astronomical units). The rules a new unit has to
follow are in the "Volume and weight conversions" section of
`calculator_spec.md`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .          # add ".[dev]" for test tooling
```

## Run

```bash
.venv/bin/flet run               # or: .venv/bin/python src/main.py
```

`src/` is Flet's import root, not a package: the modules import each other by
bare name (`from ui import AnycalcApp`), which is exactly how the packaged app
sees them.

## Tests

```bash
.venv/bin/flet test            # everything; provisions a test host, then runs pytest
.venv/bin/flet test -k engine  # the two engine test files only, no Flutter host
.venv/bin/flet test -k app     # the Flet UI tests only
```

`flet test` takes pytest flags, not file paths (select with `-k`); flags after
`--` are passed to pytest verbatim. The pure-logic tests can also be run without
Flet at all: `.venv/bin/python -m pytest -k engine`.

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

## Build a desktop package

Run from the workspace root — `[tool.flet.app]` in `pyproject.toml` points Flet
at `src/main.py`, so no `cd src` is needed:

```bash
.venv/bin/flet build linux          # artifact in build/linux/, app in build/flutter/
```

The artifact is the relocatable bundle `build/linux/` (executable `anycalc`,
`app/`, `site-packages/`, `python3.14/`, `data/`, `share/`); pass `-o <dir>` to
put it somewhere else.


Requires the Flutter SDK at the version Flet pins (managed copy in
`~/flutter/<version>`); `flet build` installs it there on demand.

Note: once a build exists, `flet run` / `python src/main.py` reuse the built
client at `build/linux/anycalc` instead of the normal desktop client — move or
delete `build/linux` (or the whole `build/` dir) to go back.


