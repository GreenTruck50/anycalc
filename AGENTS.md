If I give you future instructions, write them here.
Read DOCUMENTATION_REMINDER.txt and the documentation.

Check calculator_spec.md and make sure the spec aligns with the app. Do not remove features if they are not present in the spec - instead add that into the spec. Also add into the spec whenever a new feature or change is requested. Also if the speec contains multiple specs inside eachother meet all the requirements from all the specs. If the specs conflict, tell me.
Never change the UI based on the specs file

Use tools as much as possible and not use commands where possible.
Use ripgrep instead of grep when possible (rg command)
Fix any errors or pylance warnings if possible before finishing.
If you need clarification from me, or my reasoning doesn't make sense, ask me!
Keep pyproject.toml updated (runtime dependencies, the `[tool.flet]` build config and the `[tool.flet.app]` entry point `path = "src"` / `module = "main"`, plus the `[tool.pytest.ini_options]` config - requirements.txt is gone). There is deliberately **no `anycalc` console script**: the app is not installed as a Python package, so do not re-add `[project.scripts]`.

`src/` is Flet's import root, not a package: the modules inside it import each other by bare name (`from ui import AnycalcApp`). Never add `src/__init__.py`, a `src.` import prefix, or a `sys.path` shim - a `flet build`/`flet test` artifact flattens `src/` and gives it none. pytest gets the same import root from `pythonpath = ["src"]`, Pylance from a local `.vscode/settings.json` (`python.analysis.extraPaths = ["src"]` - that directory is gitignored, so recreate it in a fresh clone). Start the app with `flet run`, test it with `flet test` (engine-only: `flet test -k engine`).

Testing default: verify with regular Flet tooling on the host (`flet run`, `flet test`, `flet test -k engine`). Use an Android emulator for testing **only when testing on Android is requested** (on-device / mobile / APK testing) - never by default and never instead of the host suite. Instructions for both paths are in `calculator_spec.md` → *Testing* ("The host path" and "The Android emulator path").

The app targets desktop **and** mobile - never describe it as desktop-only. `src/` stays free of platform-specific code and of desktop-only dependencies; the only platform-specific calls are the desktop window size/minimum in `ui.py`, which mobile ignores.

Keep personal data out of anything tracked: no real name, e-mail address, phone number or absolute home path in files or commit messages. Identify the project by its GitHub handle instead - that is why `[tool.flet] org` is `com.github.greentruck50` and not a personal name / computer username. The same applies to git metadata: the author and committer fields of every commit are handle-only.

## Version control and GitHub identity

Anything that reads or changes state on GitHub goes through the **`gh` CLI** - `gh pr`, `gh issue`, `gh run`, `gh api`, `gh browse`, `gh repo` - never raw `git` subcommands that reach the remote and never `curl` against `api.github.com`. `gh` is authenticated as the account that owns this repository, so what it reports about who did what is the truth; verify identities with `gh api user` rather than trusting a name inside a commit. The one unavoidable exception: `gh` cannot stage, commit or rewrite local history, so `git add` / `git commit` / `git rebase` / `git push` stay necessary - keep `git` on the local side and read GitHub with `gh` instead of `git log origin/…`.

Commit identity: always use the identity already configured in `.git/config` and never invent or override one - no `--author`, no `-c user.name=…`, no `GIT_AUTHOR_*` / `GIT_COMMITTER_*` in the environment. If that identity is missing or wrong, rebuild it from `gh api user` so it is the authenticated account: `user.name = <login>`, `user.email = <id>+<login>@users.noreply.github.com` - here `GreenTruck50` and `271768285+GreenTruck50@users.noreply.github.com`. A noreply address with a made-up numeric id resolves to nobody (GitHub then prints whatever display name is in the commit as an unknown user), and a real personal name in the author field leaks personal data - both are bugs to fix, not conventions to keep.

Commit messages carry **no attribution trailers**: never `Co-Authored-By:`, `Generated with`, `Signed-off-by` or any AI / agent signature. Precedent: two commits (`a2c7729`, `d72443e`) shipped with a bogus `111801513+greentruck50@…` author and a `Co-Authored-By: Claude` trailer and had to be rewritten on 2026-10-27. If it happens again, ask first, then fix metadata-only: make a backup branch, rewrite author/committer and drop the trailer, confirm `git diff <backup> main` is empty, and `git push --force-with-lease`.
