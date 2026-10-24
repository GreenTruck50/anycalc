"""Shared setup for anycalc's test suite.

Two kinds of tests live in this directory:

* pure tests that import the engine modules (``calculate.py``,
  ``conversions.py``) in the host process and call the conversion / calculation
  engine directly;
* integration tests run by ``flet test``, which boots the *built* app (its own
  copy of ``src/``) and drives it from the host through ``flet.testing``.

Both see the app's modules by bare name, because ``src/`` is the app's import
root rather than a package: pytest puts it on ``sys.path`` through
``pythonpath = ["src"]`` in pyproject.toml, which is the very same root Flet
gives the packaged app. Nothing has to be added to ``sys.path`` by hand here.
The engines never touch the UI, and ``main.py`` is safe to import too:
``ft.run(main)`` only happens under ``__main__``.
"""
