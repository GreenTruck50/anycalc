# anycalc
[![Stars](https://img.shields.io/github/stars/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/stargazers) [![Forks](https://img.shields.io/github/forks/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/forks) [![Watchers](https://img.shields.io/github/watchers/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/watchers) [![Issues](https://img.shields.io/github/issues/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/issues) [![PRs](https://img.shields.io/github/issues-pr/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/pulls) [![License](https://img.shields.io/github/license/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/blob/HEAD/LICENSE) [![Last Commit](https://img.shields.io/github/last-commit/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/commits) [![Language](https://img.shields.io/github/languages/top/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc) [![Repo Size](https://img.shields.io/github/repo-size/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc) [![Downloads](https://img.shields.io/github/downloads/GreenTruck50/anycalc/total)](https://github.com/GreenTruck50/anycalc/releases) [![Release](https://img.shields.io/github/v/release/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/releases/latest) [![Contributors](https://img.shields.io/github/contributors/GreenTruck50/anycalc)](https://github.com/GreenTruck50/anycalc/graphs/contributors)

Calculate anything — a Flet calculator for desktop and mobile: expressions,
scientific mode, named variables, history, live unit conversions and a π it
computes for itself.

- **Documentation:** [greentruck50.github.io/anycalc](https://greentruck50.github.io/anycalc/) — built from [`docs/`](docs/) by GitHub Actions
- **Requirements:** [`calculator_spec.md`](calculator_spec.md) — what the app has to do
- **Decisions:** [`docs/Change log & decisions.md`](docs/Change%20log%20%26%20decisions.md) — every change with the reasoning behind it

## Contents

1. [What it does](#what-it-does)
2. [Unit conversions](#unit-conversions)
3. [Pi calculation](#pi-calculation)
4. [Requirements](#requirements)
5. [Setup](#setup)
6. [Run](#run)
7. [Tests](#tests)
8. [Building packages](#building-packages)
9. [Documentation](#documentation)
10. [Project layout](#project-layout)
11. [Star history](#star-history)

## What it does

- **Two pads on one display.** The regular pad is the desk layout: `+ − × ÷`, `±`,
  and `%` as a desk-calculator percent (`200+10%` is `220`, `50%` is `0.5`,
  `200*10%` is `20`). The scientific pad contains the regular rows and adds the
  function keys, where `%` is modulo (`9%2` is `1`), with a DEG/RAD angle mode.
- **A live answer while you type.** Both pads show a muted preview under the
  expression that re-evaluates on every change, and `=` promotes it to the display.
- **Decimal arithmetic.** The engine computes with `Decimal` at
  `config.DECIMAL_PRECISION` significant digits — the precision is set process-wide
  in `config.py` — rather than with binary floating point.
- **Named variables.** Keep a result under a name in the Set Variable dialog and put
  it back into an expression from the Insert Variable dialog.
- **History.** Every finished calculation becomes a card in the history drawer: tap
  its equation or its answer to put it back in the display, or copy it from the card.
- **A physical keyboard.** The real keys press the same pad a tap presses: digits,
  `+ - * / ( ) %`, `.` and `,`, plus `^` and `e` on the scientific pad, with
  `Enter` (or `=`) for `=`, `Backspace` for `⌫` and `Esc` (or `Delete`) for `AC`.
  Up and Down arrows walk past calculations back into the display.
- **A calculator memory.** `M+` and `M-` add or subtract what the display rests on,
  `MRC` puts that number back into the expression — and clears the memory when
  pressed again right after — while an `M` in the caption row says the memory is
  holding something. The regular pad always carries the three keys; a Settings
  switch adds them to the scientific pad too.
- **Live unit conversions.** Choose a value and two units and the answer re-computes
  on every keystroke, with the chain of hops the engine took shown under it.
- **π, computed by the app itself.** Anywhere from 3 to 100 000 000 decimals on the
  Pi page, with a progress card and a button that makes the finished run the π every
  calculation in the app multiplies by.
- **Copy everywhere.** Every result, the π digits and the program's own π sit behind
  one shared clipboard service.
- **Desktop and mobile from one source.** `src/` holds no platform-specific code; the
  same tree ships to a desktop bundle, an APK and an AAB.

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
the digits opens a scrolling popup that loads the next batch of decimals as you
approach the end of what is on screen, so a hundred million decimals are never put
on screen at once.

π is computed on plain Python integers by default. `gmpy2` — in the optional
`[pi]` extra, and already in `[dev]` — makes big runs far faster; it is a C
extension with no Android wheel, so it is deliberately *not* a runtime
dependency and `src/pi.py` falls back to the stdlib when it is missing.

## Requirements

Python 3.11+. The app itself needs only two packages at runtime — `flet` (the UI)
and `PyYAML` (the unit data); everything else it imports is the standard library.
Everything else lives in the optional extras declared in `pyproject.toml`:

| Extra | Brings | Needed for |
| --- | --- | --- |
| `dev` | `flet[cli,desktop,test]`, `pytest`, `pytest-asyncio`, `gmpy2` | the `flet` command, the desktop client, the test suite |
| `pi` | `gmpy2` | big π runs — the second opinion the digits are checked against, and a large speed-up |
| `docs` | `mkdocs` | building `docs/` locally |

`gmpy2` is deliberately **not** a runtime dependency: it is a C extension with no
Android wheel, and `flet build apk|aab` pip-installs the runtime list into the
artifact. `src/pi.py` falls back to stdlib integers when it is missing.

## Setup

```bash
pip install -e ".[dev]"         # everything: runtime deps + the flet command + tests
pip install -e .                # runtime deps only — this cannot run `flet run`
```

The project is intentionally **not installed as a Python package**, so there is no
`anycalc` command: `src/` is Flet's import root, and loose modules called `main`,
`ui`, `config` … in site-packages would only pollute it. `pip install` resolves the
dependencies; the app is started with `flet run` or run from a build artifact.

## Run

```bash
flet run                        # or: python src/main.py
```

`src/` is Flet's import root, not a package: the modules import each other by
bare name (`from ui import AnycalcApp`), which is exactly how the packaged app
sees them. An editor needs the same root on its path — for Pylance that is
`python.analysis.extraPaths = ["src"]` in your own editor settings, because
`.vscode/` is not tracked in this repository.

One gotcha: once a `flet build` has run, `flet run` / `python src/main.py` reuse the
built client at `build/linux/anycalc` instead of the normal desktop client — move or
delete `build/linux` (or the whole `build/` dir) to go back.

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
  adopting a finished run, and the digits popup (how much is on screen before any
  scrolling and how scrolling loads the next batch).
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

## Building packages

The same `src/` ships to desktop and to phone. Run from the workspace root —
`[tool.flet.app]` in `pyproject.toml` points Flet at `src/main.py`, so no
`cd src` is needed:

```bash
./build.py appimage       # Linux AppImage -> build/appimage/anycalc-x86_64.AppImage
./build.py deb            # Debian/Ubuntu package -> build/deb/
./build.py rpm            # RPM package -> build/rpm/
./build.py linux           # desktop bundle -> build/linux/
./build.py macos           # macOS bundle - build it on macOS
./build.py windows         # Windows bundle - build it on Windows
./build.py apk             # Android .apk
./build.py aab             # Android .aab (Play Store)
./build.py ipa             # iOS - needs macOS with Xcode
./build.py ios-simulator   # iOS simulator build
./build.py web             # static web bundle
```

`build.py` wraps `flet build`: it always runs from the workspace root and
prefers this project's `.venv/bin/flet`, so the Flet that packages the app is
the Flet the dependencies are pinned to. The app ID, product name, description,
version, license, author, and Linux categories are read from `pyproject.toml`.
The builder also owns
the build **mode**, which `flet build` has no flag for — the mode belongs to
Flutter, so it has to be forwarded as `--flutter-build-args=--debug`, and that
is easy to forget:

```bash
./build.py apk                 # release (default): AOT, smallest, production
./build.py apk --debug         # debug: quick, debuggable, `adb install -r`
./build.py aab --split-per-abi # one bundle per ABI
./build.py linux --clean       # wipe build/ first, then build
```

`--out <dir>`, `--arch arm64-v8a`, `--python-version 3.14` and `--plain` round it
out; anything after `--` goes straight to `flutter build`. Plain
`flet build <target>` still works if you want to drive it yourself.

Desktop: the artifact is the relocatable bundle `build/linux/` (executable
`anycalc`, `app/`, `site-packages/`, `python3.14/`, `data/`, `share/`).
`./build.py appimage` first makes that same Linux bundle, then wraps it in an
AppDir and runs `appimagetool`; the resulting file is
`build/appimage/anycalc-<host-architecture>.AppImage`. Install `appimagetool`
and make it available on `PATH` first, or set `APPIMAGETOOL` to its executable
path. The `--out <dir>` option selects the AppImage output directory for this
target; the intermediate Linux bundle remains in `build/linux/`. This packages
the app bundle and icon, but does not vendor GTK or other host system libraries,
so those Linux runtime libraries must be present on the machine running it.
`./build.py deb` and `./build.py rpm` also build the Linux bundle first, then
create a native package with an installed launcher, desktop entry and icon. The
`.deb` uses `dpkg-deb`; `.rpm` requires `rpmbuild`. Both targets must run on
Linux and produce packages for the host architecture. `--out <dir>` selects
the final package output directory. Packages require the system GTK 3 runtime
and do not bundle GTK or other host libraries. For `./build.py linux`,
`--out <dir>` still selects the bundle output directory.

Mobile: `apk` / `aab` go through the Flutter SDK and need an Android SDK plus a
JDK (here: `~/Android/Sdk`, `java`, `adb` on PATH); `ipa` builds only on macOS
with Xcode. `org` / `product` in `[tool.flet]` set the application id and the
app label, and `src/` contains no platform-specific code — every target packages
the same source.

Naming: a **release** Android artifact is renamed to `build/apk/anycalc.apk` —
the exact file `./test-with-emulator.sh` installs — while a **debug** artifact is
left as `build/apk/app-debug.apk`. So an emulator run after a debug build needs
`adb install -r build/apk/app-debug.apk` (or just build in the default release
mode).

Every target needs the Flutter SDK at the version Flet pins (managed copy in
`~/flutter/<version>`); `flet build` installs it there on demand. Of the targets
above, Linux and Android have been built from this workspace; the others are
documented but unbuilt here.

## Documentation

The prose documentation lives in `docs/` and is built by MkDocs from `mkdocs.yml`
beside it. `.github/workflows/docs.yml` runs `mkdocs build --strict` and publishes the
result to [GitHub Pages](https://greentruck50.github.io/anycalc/) on any push to `main`
that touches `docs/**`, `mkdocs.yml` or the workflow itself — a broken internal link
then fails the deploy instead of shipping.

| Page in `docs/` | Covers |
| --- | --- |
| `anycalc (Flet calculator app).md` | the hub: what the app is and how it behaves |
| `Source layout — modules and the Flet import root.md` | every module, its public names, and why `src/` is an import root |
| `Testing — pytest + flet test suite.md` | the host path and the Android emulator path in full |
| `Change log & decisions.md` | a running log of every change with its reasoning, dead ends included |

```bash
pip install -e ".[docs]"
mkdocs serve            # live preview
mkdocs build --strict   # what CI runs
```

`mkdocs build` writes `site/`, which is gitignored — it mirrors `docs/` word for word.
`calculator_spec.md` stays the requirements document: the docs describe what the app
is, that file says what it must be. `AGENTS.md` carries the working rules for this
repository, and `DOCUMENTATION_REMINDER.txt` is the pointer that the project notes live
in `docs/` now.

## Project layout

```
pyproject.toml              metadata, dependencies, Flet build config, pytest config
calculator_spec.md          the requirements document the app is built against
mkdocs.yml                  docs site config and navigation
docs/                       the prose documentation; published to GitHub Pages
.github/workflows/docs.yml  builds docs/ with --strict and publishes it
src/                        the app (entry point: src/main.py)
  main.py                   starts the app — it holds no behaviour of its own
  ui.py                     AnycalcApp: page setup, display state, keypad wiring,
                            drawer navigation, DEG/RAD, variables, history
  calculate.py              the expression engine both pads sit on (Decimal math,
                            the two meanings of %, the ± sign change)
  conversions.py            the unit conversion engine (YAML config, route finding,
                            formula application, the chain of hops)
  pi.py                     the pi computation (Chudnovsky + binary splitting) and
                            the one pi the program calculates with
  pi_value.py               a pi run packaged for the page — timing, progress
                            numbers, adopting a finished run
  config.py                 numeric limits, display sizes, variable names/options,
                            error messages, the path to the unit data
  styles.py                 the colour palette
  clipboard.py              the one clipboard service behind every copy button
  keypad.py                 which keys each pad shows and how a key looks
  conversion_view.py        the live conversion form and its chain cards
  pi_view.py                the pi page — digit choice, progress card, "use this
                            value", the digits popup that loads more as you scroll
  history_view.py           history cards and the history drawer
  variable_dialogs.py       the Set / Insert Variable dialogs
  assets/conversions.yaml   unit groups and the formulas between them
tests/                      the test suite — host-side; src/ is what gets packaged
                            (every file is listed under Tests above)
```

Only sources and project configuration are tracked: `build/`, `site/`, the caches and
each machine's own Python environment or editor settings stay ignored.

## Star History

<a href="https://www.star-history.com/?repos=greentruck50%2Fanycalc&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=greentruck50/anycalc&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=greentruck50/anycalc&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=greentruck50/anycalc&type=date&legend=top-left" />
 </picture>
</a>
