If I give you future instructions, write them here.
Read DOCUMENTATION_REMINDER.txt and the documentation.

Check calculator_spec.md and make sure the spec aligns with the app. Do not remove features if they are not present in the spec - instead add that into the spec. Also add into the spec whenever a new feature or change is requested. Also if the speec contains multiple specs inside eachother meet all the requirements from all the specs. If the specs conflict, tell me.
Never change the UI based on the specs file

Use tools as much as possible and not use commands where possible.
Fix any errors or pylance warnings if possible before finishing.
If you need clarification from me, or my reasoning doesn't make sense, ask me!
Keep pyproject.toml updated (runtime dependencies, the `[tool.flet]` build config and the `[tool.flet.app]` entry point `path = "src"` / `module = "main"`, plus the `[tool.pytest.ini_options]` config - requirements.txt is gone). There is deliberately **no `anycalc` console script**: the app is not installed as a Python package, so do not re-add `[project.scripts]`.

`src/` is Flet's import root, not a package: the modules inside it import each other by bare name (`from ui import AnycalcApp`). Never add `src/__init__.py`, a `src.` import prefix, or a `sys.path` shim - a `flet build`/`flet test` artifact flattens `src/` and gives it none. pytest gets the same import root from `pythonpath = ["src"]`, Pylance from a local `.vscode/settings.json` (`python.analysis.extraPaths = ["src"]` - that directory is gitignored, so recreate it in a fresh clone). Start the app with `flet run`, test it with `flet test` (engine-only: `flet test -k engine`).

The app targets desktop **and** mobile - never describe it as desktop-only. `src/` stays free of platform-specific code and of desktop-only dependencies; the only platform-specific calls are the desktop window size/minimum in `ui.py`, which mobile ignores.
