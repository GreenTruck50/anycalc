How `src/` is organised after the module split, and the packaging fact that decides how the modules are allowed to import each other. Updated 2026-10-24 for the switch to the stock Flet import convention.

## Module map (`src/`, 11 modules — there is no `__init__.py`)

| Module | Owns | Entrypoints other modules use |
| --- | --- | --- |
| `main.py` | The entry only: `main(page)`, `run_app()`, the `__main__` guard | — |
| `config.py` | Numeric limits (`DECIMAL_PRECISION`, `MAX_*`), display + live-preview sizes and the morph timing, the error messages, `VARIABLE_OPTIONS` / `VARIABLE_NAMES`, `CONVERSION_CONFIG_PATH`; sets the process-wide `Decimal` precision | constants; no Flet import |
| `calculate.py` | The expression engine both pads sit on: preprocessing, the two meanings of `%`, the precedence ladder, `Decimal` evaluation | `calculate(text, scientific, degrees, variables)`, `is_number`, `toggle_sign`, `apply_percent_operators` |
| `conversions.py` | The conversion config, route finding (forward first, `MD` formulas may be inverted, `UD` never), formula application, the reported chain of hops | `load_conversion_config()`, `convert_units()`, `find_conversion_path()`, `format_conversion_value()`, `ConversionStep`, `ConversionOutcome` |
| `styles.py` | The colour palette, so one hex value cannot drift between controls | colour constants |
| `keypad.py` | Which keys each pad shows and how a key looks; the regular rows are part of the scientific pad | `REGULAR_ROWS`, `SCIENTIFIC_ROWS`, `DIALOG_KEYS`, `key_color()`, `make_key()` |
| `clipboard.py` | The single `ft.Clipboard` behind every copy button | `ClipboardService` |
| `history_view.py` | History card + history drawer | `build_history_card()`, `build_history_drawer()` |
| `variable_dialogs.py` | Set Variable / Insert Variable dialogs | `open_set_variable_dialog(app)`, `open_insert_variable_dialog(app)` |
| `conversion_view.py` | The conversion entries and the live conversion form in the main content area | `ConversionView` |
| `ui.py` | The app object: page setup, display state (expression, result mode, DEG/RAD, named variables, history), the live preview and its morph, keypad dispatch, mode/content switching | `AnycalcApp` |

Names in this table were corrected on 2026-10-24 against the actual source: the app class is `**AnycalcApp**` (earlier notes said `CalculatorApp`), the conversion call is `**convert_units()**` (not `convert()`), and the dialog functions are `**open_set_variable_dialog()**` **/** `**open_insert_variable_dialog()**` (not `prompt_variable()` / `insert_variable()`).

## Dependency direction (one-way, so the engines stay testable)

*   `config` ← `calculate`, `conversions` (the engines import nothing else, and **no Flet**, so they import and test without an app host).
*   engines + `styles`, `keypad`, `clipboard`, `history_view`, `variable_dialogs`, `conversion_view` ← `ui`.
*   `main` ← `ui` only. Views and dialogs receive what they need (page, controls, callbacks, or the app object) instead of reaching into an app closure, which is what let the closure-based single file become a class plus plain functions.

## The Flet import root — the rule that matters (stock convention since 2026-10-24)

*   `[tool.flet.app] path = "src"` makes Flet treat `**src/**` **as the artifact's import root**. The packager is `package_python_app()` (`flet_cli/commands/build_base.py:2514`), which shells out to `dart run serious_python:main package <app dir>`; the result is staged to `build/python-app/` (verified at `build_base.py:2843`, passed on as `SERIOUS_PYTHON_APP`). Inside it the modules sit side by side: `main.pyc, calculate.pyc, keypad.pyc, conversions.pyc, styles.pyc, ui.pyc, config.pyc, …` plus `assets/conversions.yaml`. **That folder, not the project root, is what the runner puts on** `**sys.path**`**.**
*   So every module of the app imports its siblings **by bare name** — `from ui import AnycalcApp`, `from config import …`, `import calculate`. That is the stock Flet convention: `flet create` scaffolds `src/main.py` with **no** `**src/__init__.py**` and puts `pythonpath = ["src"]` in its pytest config, i.e. `src/` is an import root, never a package.
*   Each way of starting the app supplies that root itself: `flet run` / `flet build` from `[tool.flet.app] path`, `python src/main.py` from `sys.path[0]`, pytest from `pythonpath = ["src"]` in `[tool.pytest.ini_options]`. Pylance needs the equivalent — `"python.analysis.extraPaths": ["src"]` in `.vscode/settings.json`, otherwise all bare-name imports go red.
*   **No longer allowed**: `src.`\-prefixed imports, `src/__init__.py`, and any `sys.path`/`sys.modules` fix-up code. On 2026-10-24 the `ensure_src_package()` shim was deleted from `main.py`, the `REPO_ROOT` insert from `tests/conftest.py`, and the `anycalc` console script (`[project.scripts] anycalc = "src.main:run_app"`) from `pyproject.toml`; `[tool.setuptools]` now declares `packages = []` / `py-modules = []` so a `pip install` only resolves dependencies rather than dropping loose `main`/`ui`/`config` modules into site-packages.
*   Open conflict to remember: the AGENTS.md rule _"Keep pyproject.toml updated (…, the_ `_anycalc_` _entry point …)"_ was written for the console script. The user chose the stock convention knowing the console script goes away; the **Flet** entry point (`[tool.flet.app] module = "main"`) is still declared. AGENTS.md has not been amended.
*   Assets keep working because `config.py` builds `CONVERSION_CONFIG_PATH` from `Path(__file__)`, and the packager keeps `assets/` next to the modules — subdirectories survive the copy, which is also why `assets/conversions.yaml` is where the app expects it. `__pycache__` is excluded from the bundle by default.
*   Historical note: before 2026-10-24 the tree used absolute `src.<module>` imports, which required a shim in `main.py` to register `src` as a package rooted at the flattened artifact directory, because that root has no `src` package. The shim worked but the layout was not what Flet scaffolds; it was removed rather than kept.

## Checking a change like this

1.  `cd src && python -c "import main, ui, calculate, conversions, conversion_view, config, styles, keypad, clipboard, history_view, variable_dialogs"` — proves the bare-name imports resolve from the app root.
2.  `python -m pytest -k engine` from the workspace root — proves `pythonpath = ["src"]` gives the host the same root (178 tests).
3.  `flet test` — it builds the app first, so it is the only command that exercises the packaged layout (never pass file paths; select with `-k`).