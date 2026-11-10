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
- [ ] Restore the last-used unit pair and currency pair on launch (31)
- [ ] Favourite / pinned unit pairs at the top of the conversions menu (32)

## Conversions & currency

- [ ] Search / filter box over the unit menu - conversions.yaml is 1803 lines of units, scrolling is losing (33)
- [ ] Missing unit groups: speed, pressure, power, angle, data rate, mass flow (34)
- [ ] Custom user-defined units / formulas stored alongside conversions.yaml (35)
- [ ] Validator / test that walks the whole formula graph in conversions.yaml and proves every unit in a group is reachable from every other (MD reversal is silent when it fails) (36)
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