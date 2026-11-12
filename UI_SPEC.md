# UI_SPEC — what the screens actually look like

This file describes the UI as `src/` builds it today. It is a description, not a
brief: the code is not written to match this file, and a screen that changes gets
written up here afterwards (`AGENTS.md`: "Never change the UI based on the specs
file"). `calculator_spec.md` says what a feature has to *do*; this says what the
user *sees*, in which order, and which control is responsible.

Who builds what:

| Part | Owner |
| --- | --- |
| Shell, header, drawers, page switching | `src/ui.py` (`AnycalcApp`) |
| Regular + scientific keypad | `src/keypad.py` |
| Unit conversion form (all fifteen groups) | `src/conversion_view.py` |
| Currency conversion form | `src/currency_view.py` |
| Pi page | `src/pi_view.py` |
| History drawer | `src/history_view.py` |
| Colours, sizes | `src/styles.py`, `src/config.py` |

## The shell

`AnycalcApp.build()` puts exactly two things on the page, inside a `ft.SafeArea`
so the OS status bar, notch and navigation bar never sit on top of the content:

```
SafeArea
└── Column(spacing 0, expand)
    ├── header                 (the Row described below)
    └── content_area           (exactly one page at a time)
```

* Desktop only: `window.width = 400`, `window.height = 780`,
  `min_width = 320`, `min_height = 500`. Mobile ignores these.
* The header and `content_area` start `disabled` and are enabled once the saved
  state has been read (`page.run_task(self.load_saved_data)`), so nothing can be
  pressed against data that has not arrived yet.
* `content_area` is a `Column` holding one child: the calculator view
  (`[display_panel, keypad]`) or the `Column` returned by a view's `build()`.
  Changing page replaces that single child; the header never changes.

### Header

`ft.Row`:

1. `ft.IconButton(key="menu-button", icon=MENU, tooltip="Calculator menu")` —
   opens the start (navigation) drawer.
2. `ft.Column`: the title `ft.Text("AnythingCalculator", size=19, bold)` and under
   it `self.status`, a 12 px muted caption that names the page on screen:
   `REGULAR MODE`, `SCIENTIFIC MODE`, `UNIT CONVERSION`, `CURRENCY CONVERSION`
   or `PI CALCULATION`.
3. `ft.IconButton(key="settings-button", icon=SETTINGS, tooltip="Settings")`.
4. `ft.IconButton(icon=HISTORY, tooltip="Calculation history")` — opens the end
   (history) drawer.

### Navigation drawer (`page.drawer`, a `ft.NavigationDrawer`)

In order: a title block ("AnythingCalculator" / "Calculate anything."), then

| Entry label | `key` |
| --- | --- |
| Regular Calculator | `drawer-regular-calculator` |
| Scientific Calculator | `drawer-scientific-calculator` |
| one entry per conversion group in `src/assets/conversions.yaml` (fifteen) | `drawer-<name lower-cased, spaces as hyphens>`, e.g. `drawer-volume-conversion` |
| Currency Conversion | `drawer-currency-conversion` |
| Pi Calculation | `drawer-pi-calculation` |

The list does not scroll on a short window, so the last entries stop rendering —
which is why the app-host tests in `tests/test_app.py` skip the Force page and
the Pi page.

### History drawer (`page.end_drawer`)

Built by `history_view.build_history_drawer()`: a list of cards, each showing the
expression and the answer; tapping either puts that expression back on the
display, and each card carries a copy button. A muted notice
(`key="history-scope-notice"`) says history only applies to the two calculators
whenever a non-calculator page is open.

## The calculator page (Regular / Scientific)

`self.calculator_view = ft.Column([display_panel, keypad], spacing=12, expand=True)`.

### Display panel

`ft.Container(bgcolor=PANEL_BACKGROUND, border_radius=18, padding=16, height=168)`
holding a `Column(alignment=SPACE_BETWEEN)`:

1. Caption `ft.Row`: `ft.Text("EXPRESSION", 11px muted)`, a spacer, the display
   copy button (`clipboard.make_button`, tooltip "Copy displayed value"), and the
   angle button (`ft.TextButton` labelled `DEG` / `RAD`).
2. The display itself — `ft.TextField(key="display", value="0")`, right-aligned,
   `DISPLAY_TEXT_SIZE`, `NoInputBorder`, `content_padding=0`, `expand=True`.
   Typing in it edits the expression (`on_change`); `on_submit` (Enter) does what
   `=` does; focusing it selects the result.
3. The live preview: a muted right-aligned `ft.Text` in `self.preview_slot`,
   visible only while the expression has an answer. It re-evaluates on every
   change and animates (`PREVIEW_MORPH_MS`, ease-out) when `=` promotes it into
   the display.
4. `self.memory_status` (`"M = 42"`) and `self.variable_status` (the set
   variables as `name = value`). Both live on the same line under the display,
   because that line belongs to whichever shared pad row is up — only one of the
   two is ever visible.

### Keypad

`self.keypad` is a `ft.Column(spacing=8, expand, scroll=AUTO)` that
`rebuild_keypad()` fills for the current mode. Every key is a
`ft.Container(key=f"key-<label>", height=54, border_radius=14, expand=True,
ink=True)` with centred text (19 px, or 14 px for labels over 8 characters). The
`key-…` handles are what the tests drive.

Regular rows (`keypad.REGULAR_ROWS`) — the whole pad on the Regular Calculator:

```
AC  ⌫   (   )   ±   %
7   8   9   ÷
4   5   6   ×
1   2   3   −
0   .   =   +
```

The scientific rows (`keypad.SCIENTIFIC_ROWS`) are the only thing the Scientific
Calculator adds, and they go on top:

```
sin  cos  tan  √
log  ln   𝜋    e   ^
```

One slot of the pad is shared by two rows (`pad_rows()` assembles it): the memory
row `MRC  M+  M-  MCLR` and the variable row
`Set Variable  Insert Variable  Clear Variables`. The Regular Calculator always
carries the memory row; the Scientific Calculator carries the variable row unless
the Settings switch "Memory keys on the scientific pad" puts the memory row there
instead, which takes the named variables out of the page.

Key colours (`keypad.key_color`): `=` is `ACCENT`; `AC` and `⌫` are `KEY_DANGER`;
`÷ × − + % ±` are `KEY_OPERATOR`; the scientific, memory and variable keys are
`KEY_OPERATOR` (they are the band above the digits); digits are `KEY_DEFAULT`.

`%` is the desk-calculator percent on the regular pad (`200+10%` → `220`) and
modulo on the scientific pad (`9%2` → `1`).

### Physical keyboard

`keypad.KEYBOARD_KEYS` maps real keys onto pad keys, and the app refuses anything
the pad on screen does not carry — which is how `^`, `e` and `√` stay
scientific-only. `Enter` / `=` press `=`, `Backspace` presses `⌫`, `Esc` /
`Delete` press `AC`, and `Up` / `Down` walk the stored history into the display.

## The conversion page — one layout for all fifteen groups

`ConversionView.build()` returns the same `Column` for every group (Length, Time,
Temperature, Data, Volume, Area, Weight, Energy, Force, Speed, Pressure, Power,
Angle, Data Rate, Mass Flow). Nothing in it is group-specific: the title, the
description, the icon and the unit list come from `src/assets/conversions.yaml`.
Top to bottom:

| Control | `key` | What it is |
| --- | --- | --- |
| Title row | — | the group's icon (28 px, `ACCENT`) and `conversion["name"]`, 22 px bold |
| Description | — | `conversion["description"]`, muted |
| Value field | `conversion-value` | label "Value", numeric keyboard, autofocus, `on_change` re-converts |
| From dropdown | `conversion-from` | label "From"; one option per unit, text `"<name> (<symbol>)"`, option `key` = unit id; `on_select` re-converts |
| Swap button | `conversion-swap` | `ft.OutlinedButton` "Swap units", `SWAP_HORIZ` icon, tooltip "Swap the From and To units" |
| To dropdown | `conversion-to` | the same option list as From |
| Guidance block | `conversion-guidance` | "UNIT GUIDANCE" (10 px) plus one line per selected unit that carries a guidance note in the YAML, duplicates dropped; hidden when neither unit has one |
| Hint row | — | small `SWAP_HORIZ` icon + "Converts as you type or change units" |
| Result field | `conversion-result` | read-only, label "Result", copy button as its suffix (tooltip "Copy converted value") |
| Chain card | `conversion-chain` | header `CHAIN OF OPERATIONS (N steps)` (10 px) plus one card per hop the engine took — number, `Unit → Unit`, the value at that step and a "View formula" button that reveals the formula applied; when both units are the same it says "Same unit - the value is passed through unchanged."; hidden until there is an answer |

Each dropdown rides in a `ft.Row` of its own with `expand=True` — that is what
makes Flutter stretch the box to the page width instead of to its longest unit
name. Everything on the page stretches to the content area's width
(`horizontal_alignment=STRETCH`).

While typing: an empty or half-typed value (`-`, `3.`, `abc`) clears the result
without complaining; a conversion the engine refuses (`ValueError`,
`DivisionByZero`, `Overflow`) becomes the result field's error text.

## The currency page

`CurrencyConversionView.build()` has the same shape and the same dropdown
stretching trick:

| Control | `key` | What it is |
| --- | --- | --- |
| Title row | — | `CURRENCY_EXCHANGE` icon + "Currency Conversion", 22 px bold |
| Description | — | "Convert using daily exchange rates, including supported cryptocurrencies and metals." |
| Value field | `currency-value` | label "Value", numeric keyboard, autofocus, `on_change` re-converts |
| From dropdown | `currency-from` | label "From", filled once the rate table arrives |
| Swap button | `currency-swap` | "Swap currencies", `SWAP_HORIZ` icon |
| To dropdown | `currency-to` | the same options as From |
| Status row | `currency-status`, `currency-retry` | "Loading available currencies…" while fetching; on failure the reason plus a Retry button (hidden until then) |
| Rate date | `currency-rate-date` | hidden until a rate table arrives |
| Hint row | — | "Converts as you type or change currencies" |
| Result field | `currency-result` | read-only, copy button as its suffix |

The dropdowns are built empty. Opening the page runs `load_currencies()` through
`page.run_task`; when the table arrives the options are filled and the opening
pair is applied. Replies are token-guarded (`request_token`) and the app marks the
view inactive (`_deactivate_currency_view`) as soon as the page is left, so a slow
response cannot write into a page that is gone.

## Which pair a conversion or currency page opens on

Both pages reopen on the pair they were last left on, across page changes and
restarts.

* The app holds `self.unit_pairs: dict[str, tuple[str, str]]` (conversion name →
  `(source unit id, target unit id)`) and `self.currency_pair: tuple[str, str] |
  None` in `src/ui.py`.
* `open_conversion()` hands the page that name's pair as `saved_pair` plus an
  `on_units_changed` callback; `open_currency_conversion()` does the same with
  `saved_pair` and `on_pair_changed`.
* **The view decides what to open on**, because only the view has the option
  list: `ConversionView.opening_pair()` uses the saved pair only if both ids are
  still units of that group, otherwise the group's first two units (a one-unit
  group opens on that unit in both boxes). `CurrencyConversionView.opening_pair()`
  uses the saved pair only if today's rate table still offers both codes,
  otherwise US dollar → euro.
* **The app decides what to remember**, because the view owns no storage.
  `select_unit()` and `select_currency()` report the pair before re-converting,
  and the Swap buttons report the swapped pair — a swap is a choice of pair like
  any other. `remember_unit_pair()` / `remember_currency_pair()` write it and save
  the state, but only when the pair actually changed.
* Storage: `AppState.unit_pairs` and `AppState.currency_pair` in
  `src/data_storage.py`, written as JSON arrays —
  `"unit_pairs": [["Volume Conversion", "volume_liter", "volume_cubic_meter"]]`,
  `"currency_pair": ["jpy", "chf"]` or `null`. A save written before this feature
  decodes to "no pairs remembered", and if a save repeats a conversion name the
  last row wins.
* Storage only checks that a row is three non-empty strings; whether a unit id
  really exists is never checked there or in the app — that is the view's
  `opening_pair()` test.
* Settings → "Reset all app data" clears both, so every page goes back to its
  default pair.

## The Pi page

`PiView.build()` assembles its tree once and hands back the same `root` on every
reopen, so finished digits, progress numbers and the typed digit count are still
there after leaving the page. Handles: `pi-current`, `pi-current-note`,
`pi-view-current`, `pi-digits` (preset dropdown), `pi-digits-exact` (exact count
field), `pi-plan`, `pi-precision`, `pi-compute`, `pi-stop`, `pi-progress`,
`pi-percent`, `pi-terms`, `pi-phase`, `pi-speed`, `pi-estimate`, `pi-result`,
`pi-status`, `pi-view-digits`, `pi-adopt`, plus the digit-search field and its
result line.

## The settings dialog

`ft.AlertDialog(key="settings-dialog", modal=True, title="Settings")` whose content
is a scrolling `Column` (height 460). Every control applies what it changed
immediately — there is no Apply button; the actions are `settings-close` ("Close")
and `settings-reset` ("Reset to defaults").

| Setting | `key` |
| --- | --- |
| Theme (System first, then the built-in palettes) | `settings-theme-dropdown` |
| "Memory keys on the scientific pad (replaces the variable keys)" — a `Switch` beside a tappable label, wrapped in a `Semantics` node so a screen reader still gets the sentence | `settings-memory-keys` |
| Decimal places / significant figures / scientific-notation threshold / rounding mode | `settings-precision-decimals`, `settings-precision-significant-figures`, `settings-precision-scientific-notation`, `settings-precision-rounding` |
| History length ("Keep 10 / 25 / 50 / 100") | `settings-history-length` |
| Clear history / Reset all app data (the latter opens a confirmation) | `settings-clear-history`, `settings-reset-all-data` |
| Primary and secondary color — only for the Custom theme; each is a dropdown whose "Custom color" entry reveals a color picker | `settings-primary-color…`, `settings-secondary-color…` (`-group`, `-value`, `-picker`) |

## Test handles

Every `key=` above is a stable handle, not styling: the app-host tests in
`tests/test_app.py` and the view tests in `tests/` address controls through them
(`display`, `key-7`, `drawer-volume-conversion`, `conversion-swap`, `currency-from`,
…). Renaming one means changing the tests with it.
