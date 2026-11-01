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
- Offer a "Swap units" button on the form that exchanges the From and To
  selections and immediately re-converts the value already in the field, so
  turning a conversion around needs no dropdown interaction at all.
- Lay the conversion page out horizontally to the width of the content area: the
  value field, the two unit dropdowns, the swap button, the result field and the
  chain cards all stretch to the available width - the way the history cards in
  the drawer do - rather than carrying fixed widths of their own.
- Reach that width on the dropdowns by wrapping each one in a row: a bare Flet
  `Dropdown` sizes its painted box to its own content and ignores the parent
  column's cross-axis stretch, which is why the value field grows on a full
  screen while a bare dropdown stays put.

- Show the selected conversion form in the main content area used by the
  calculators, rather than in a popup.
- Head that form with the group's icon and name from the YAML, and put the group's
  description line under it, so the entry and the page say the same thing.
- Say on the form itself that it works without a button: a muted hint under the
  fields reads "Converts as you type or change units".
- Keep the result field read-only and put its copy button inside it as a suffix,
  so there is no separate control drifting next to it.

## Volume and weight conversions

- Offer a "Volume Conversion" group covering metric cubic units, metric liquid
  units, metric and US culinary measures, US customary and imperial cubic and
  liquid units, US dry units, the petroleum barrel and the gas-industry trade
  measure ccf (hundred cubic feet).
- Keep that group's unit list ordered so measures of a kind sit next to each
  other, because the list order is the order both unit dropdowns show: cubic
  units first (metric, then imperial / US customary), then the metric liquid
  units, then the culinary measures (metric spoons and cups, then the US
  customary liquid ones with the US legal cup beside the US cup), then the US
  dry units, then the imperial liquid units. The group still opens on its first
  two units, cubic millimetre to cubic centimetre.
- Define the hundred cubic feet (ccf), the unit a natural-gas bill is written in,
  by exactly 100 ft3 - an integer hop off the cubic foot - and list it directly
  after the cubic foot, so a ccf reaches every other volume unit exactly (1 ccf
  is 2831684.6592 cm3).
- Offer a "Weight Conversion" group covering metric units, avoirdupois units,
  troy units and apothecaries' units.
- Cover the Australian and older British culinary measures in the Volume group:
  the Australian and New Zealand tablespoon of 20 mL - twice the metric
  tablespoon every other metric country uses, so using 15 mL flattens an
  Australian recipe - and the 10 mL dessertspoon of older British and
  Australian cookbooks. Define both directly in milliliters, by exact integers.
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

## Area conversions

- Offer an "Area Conversion" group whose drawer entry uses the `ASPECT_RATIO`
  icon and whose description reads "Convert between square meters, square feet,
  acres, hectares, etc.".
- Cover metric square units (square micrometre, square millimetre, square
  centimetre, square decimetre, square metre, square kilometre), the metric land
  units are and hectare, the customary square units square inch, square foot,
  square yard and square mile, and the land measures acre, rood and square rod.
- Open the form on the group's first two units, square millimetre to square
  centimetre, and convert 100 mm2 to exactly 1 cm2 there.
- Use the legal definition of each unit as the formula factor and never a rounded
  approximation of it: 1 in = 2.54 mm (so 1 in2 = 0.00064516 m2 exactly),
  1 ft2 = 144 in2, 1 yd2 = 9 ft2, 1 mi2 = 3097600 yd2, 1 acre = 4840 yd2,
  1 acre = 4 rood = 160 sq rod, 1 rood = 40 sq rod, 1 are = 100 m2 and
  1 ha = 100 a.
- Route the land measures acre -> rood -> square rod instead of wiring the square
  rod to the square yard: 1 yd2 = 30.25 sq rod, and walking that edge backwards
  would have to divide by 121, which is not a decimal - so square rod -> square
  yard would come out repeating even though its exact factor, 30.25, terminates.
  The chained form keeps every hop an integer multiply or an integer divide that
  the route's own exact factor absorbs, the same rule the Volume group follows
  with mi3 -> yd3 -> ft3 -> in3.
- Hold the Area group to the same exactness sweep as Volume and Weight: of the
  210 ordered pairs of its 15 units, the 139 whose true factor is a terminating
  decimal must come out bit for bit right. The remaining 71 - every pair that
  crosses the metric/customary boundary, plus ratios such as in2 -> ft2 whose
  exact factor is 1/144 - repeat and are left to the engine's 50-digit rounding.
- Keep Area units inside the Area group: an area unit and a length or volume unit
  stay an error, the way Volume and Length do.

## Energy and force conversions

- Offer an "Energy Conversion" group whose drawer entry uses the `BOLT` icon and
  whose description reads "Convert between joules, calories, kilowatt-hours, BTU,
  therms, etc.".
- Cover metric energy units (joule, kilojoule, megajoule, gigajoule and the CGS
  erg), the three legal calories and the kilocalorie, the electrical watt-hour
  with its kilo- and megawatt-hour, the International Table and thermochemical
  British thermal units, the therm, the quad, the horsepower-hour, the
  foot-pound-force and the electronvolt.
- Offer a "Force Conversion" group whose drawer entry uses the `FITNESS_CENTER`
  icon and whose description reads "Convert between newtons, pound-force,
  kilogram-force, dynes, kips, etc.".
- Cover metric force units (newton, kilonewton, meganewton and the CGS dyne), the
  gravitational metric units kilogram-force, gram-force and tonne-force, and the
  imperial / US customary pound-force, ounce-force, poundal, short ton-force,
  long ton-force and kip.
- Order each new group's unit list so measures of a kind sit next to each other -
  SI prefixes together, then the CGS and gravitational metric units, then the
  customary ones - because that list is the order both unit dropdowns show, and
  open each form on its first two units: joule to kilojoule, newton to kilonewton.
- Use the defined constant as the formula factor and never a rounded approximation
  of it: 1 cal (IT) = 4.1868 J, 1 cal (thermochemical) = 4.184 J, 1 cal (15 C) =
  4.1855 J, 1 Btu (IT) = 1055.05585262 J, 1 therm = 100000 Btu (IT), 1 quad =
  1e15 Btu (IT), 1 Wh = 3600 J, 1 hp-h = 1980000 ft-lbf, 1 eV = 1.602176634e-19 J,
  1 kgf = 9.80665 N (standard gravity being exactly 9.80665 m/s2), 1 lbf =
  4.4482216152605 N, 1 pdl = 0.138254954376 N, 1 dyn = 0.00001 N, 1 kip =
  1000 lbf, 1 short ton-force = 2000 lbf and 1 long ton-force = 2240 lbf.
- Reach the large industry units by chained integers off their base unit rather
  than by one long decimal: the therm and the quad hang off the Btu (IT) by 100000
  and 1e15, and the horsepower-hour off the foot-pound-force by 1980000. The quad
  alone would need a 19-digit factor, past what the engine can parse.
- Write a factor that is a product of two exact short literals as that product
  when the single equivalent decimal is too long for a literal: the
  foot-pound-force is `x * 4.4482216152605 * 0.3048`, because its exact value
  1.3558179483314004 J has 17 significant digits. `Decimal` multiplies both forms
  exactly, and reversing the hop divides by each factor in turn.
- The only Energy unit whose stored factor cannot be written exactly is the
  thermochemical Btu: it is the heat for a pound of water per degree Fahrenheit,
  so the 5/9 of the Fahrenheit step leaves a repeating decimal
  (1054.3502644888... J). Its literal carries the most digits the engine can parse
  (1054.35026448889, 15 significant digits) and a test measures that against the
  exact rational. Every other Energy and Force factor is an exact decimal.
- Hold both groups to the same exactness sweep as Volume, Area and Weight: of the
  342 ordered pairs of Energy's 19 units, the 112 whose true factor is a
  terminating decimal, and of the 156 ordered pairs of Force's 13 units, the 85
  whose true factor is one, must come out bit for bit right.
- Keep Energy and Force apart: there is no bridge between a joule and a newton,
  and none between a cubic foot of gas and a therm, even though ccf and the therm
  are both gas-bill units - the guidance lines say how they relate instead.
- With the two new groups the drawer lists nine conversions, so its entry list is
  taller than the window and the last entries are reached by scrolling - they live
  in a list the drawer scrolls, not in one that truncates. The order the entries
  appear in is the order `conversions.yaml` lists the groups. To keep as many
  entries above that fold as possible, the drawer carries no footer line: the
  "Calculate anything." tagline sits under the "AnythingCalculator" title at the
  head of the drawer instead.
- Below the conversions, a second heading "Other" introduces destinations that
  are not unit conversions - currently the one Pi Calculation entry. A heading is
  a caption, not a selectable row: it must not shift what the drawer's index
  means, so selecting an entry resolves to calculators, then conversions, then
  the "Other" pages in the order they are listed.

## Unit guidance notes

- A unit may carry a `guidance` line in `src/assets/conversions.yaml`: one short
  sentence saying which country or which kind of source actually uses that unit,
  so a reader can tell from where a recipe comes which of the same-named units to
  pick. A US cup is 236.6 mL, an Australian one 250 mL, and a US tablespoon 14.8
  mL against the Australian 20 mL.
- The conversion form shows the guidance of the two selected units under the unit
  dropdowns, behind a "Unit guidance" caption, each line naming the unit it
  belongs to. Units without a guidance line add nothing, so groups such as Weight
  show no block at all.
- Refresh the notes whenever either unit changes, including on the swap button,
  and show them for the pair the page opens on - independently of the value: an
  empty or half-typed value clears the result and the chain but never the notes.
- Repeat nothing: two selected units carrying the same sentence produce one line,
  and when neither unit carries a note the caption goes with them rather than
  leaving an empty block behind.
- A `guidance` value must be non-empty text or loading the configuration fails.

## Conversion chain of operations

- Below the conversion result, show the chain of operations that produced it: a
  heading - written in the app's caption spelling, "CHAIN OF OPERATIONS (N steps)"
  - and one card per formula hop, in the order the hops were applied.
- Each hop card is numbered in hop order and names the hop by unit name and symbol
  (for example "1. Centimeter (cm) → Meter (m)") and shows that hop's input and
  output values ("2500 → 25").
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

## System status bar

- The app does not hide the mobile status bar; it keeps the bar and the app clear
  of each other. The whole window sits inside a safe area, so the header row is
  inset below the status bar, the display cutout and the navigation bar instead of
  being drawn underneath them.
- The status bar and the system navigation bar are painted in the app's background
  colour with light icons, so they read as part of the app rather than floating
  over it in platform colours.
- A safe area has nothing to avoid on desktop and web, so the window is unchanged
  there.

## Calculator navigation

- Group the Regular Calculator and Scientific Calculator destinations under a
  Calculators heading in the navigation drawer, separate from Unit Conversions.
- Head that drawer with the app title and, directly under it in the smaller muted
  caption style the app bar's mode line uses, the "Calculate anything." tagline -
  the tagline is part of that heading, not a line at the foot of the list.
- Selecting either calculator returns the main content area to that calculator.

## Calculator keypad

- The Regular Calculator keypad puts `AC`, backspace (`⌫`), `(`, `)`, `±` and `%`
  in one utility row above the digits `0-9`, `.`, `=` and the operators `÷`, `×`,
  `−`, `+`.
- The Scientific Calculator keypad keeps those rows and adds `sin`, `cos`, `tan`,
  `√`, `log`, `ln`, `𝜋`, `e`, `^` and the two variable buttons above them.
- The pi key is labelled with the mathematical italic small pi (U+1D70B) rather
  than the plain Greek letter (U+03C0), and pressing it appends the engine's own
  `pi` name to the expression - the display reads `pi`, never the glyph - so the
  key's test id is `key-𝜋`.
- A key appears on the pad exactly once: the scientific rows add only what the
  regular rows lack, so scientific mode does not show a second `(`, `)`, `%` or
  `±`, and every keypad control keeps a unique `key-<label>` id.
- Adding keys must not make the keypad taller: the regular pad stays at five rows
  (the utility keys share the top row) and the scientific pad at eight.
- Every key acknowledges a press visually: a Material ink ripple spreads through
  the tile while it is held, the same feedback the menu button, the history button
  and the dialog buttons give. A key is a plain tap tile, so without that ripple
  the pad would look dead next to those buttons - pressing one must be visible on
  the key itself, not only in the display that changes.
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

## Expression engine

- Both pads sit on one engine (`src/calculate.py`): an expression is parsed with
  `ast` and evaluated on `Decimal` values, so the precedence is the ordinary
  PEMDAS/BODMAS one and nothing is rounded through a float on the way.
- Every calculation runs at `config.DECIMAL_PRECISION` significant digits (500
  today). The Decimal context is process-wide, so it is set once in `config.py`
  and both engines reach it from there.
- `^` is the power key and reaches the parser as `**`; an exponent past
  `config.MAX_EXPONENT` reports "Exponent too large", and an expression longer
  than `config.MAX_EXPRESSION_LENGTH` reports "Expression too long".
- Only the Scientific Calculator evaluates names and calls: `sin`, `cos`, `tan`,
  `√` (stored as `sqrt(`), `log`, `ln`, the constants `pi` and `e` and any named
  variable that has been set. On the Regular Calculator a name or a call is not
  arithmetic and reports "Invalid expression" - only numbers, brackets and the
  arithmetic operators are read there.
- A result is formatted for the display rather than printed raw: an integral
  answer loses its decimal point, any other answer has its trailing zeros stripped,
  and the number is never shown in scientific notation.
- A calculation that cannot be carried out reports one of the fixed error strings
  listed in `config.ERROR_MESSAGES` ("Can't divide by 0", "Number Overflow",
  "Invalid result", "Exponent too large", "Expression too long", "Unknown
  constant", "Invalid function", "Invalid operator", "Invalid number", "Invalid
  expression", "Error") - never a Python exception name or a traceback.
- The engine takes pi from one place, the value the program calculated (see "Pi
  calculation"), and a caller - a test - can hand it its own pi instead.

## Calculator display and typing

- The display is an ordinary editable text field and not a label, so an
  expression can be typed as well as pressed; the ASCII spellings of the operators
  (`+ - * / ^ %`) are accepted next to the labelled `×`, `÷` and `−`.
- The caption above the display names the state it is in: "EXPRESSION" while an
  expression is being entered, "RESULT" once the display rests on an answer.
- An empty display shows `0`.
- After `=` the next key decides what happens to the answer: an operator (`+`,
  `-`, `−`, `×`, `÷`, `^`, `%`) continues from it, `AC` clears it, and any other
  key starts a new entry.
- Tapping the display while it rests on a result selects the whole number, so a
  new entry can be typed straight over it.
- A rejected calculation shows its error string in the display, and the next key
  pressed - including `±` and backspace - clears the error instead of editing it.

## Angle mode

- The display's caption row carries a button that switches between `DEG` and
  `RAD`; the label always states the mode currently in force, and the app starts
  in `DEG`.
- The mode applies to `sin`, `cos` and `tan`, to the live preview, and to the
  value entered in the Set Variable dialog, which is evaluated by the same engine.
- Switching modes re-evaluates the live preview, so the answer under the display
  changes with it.

## Named variables

- The Scientific Calculator carries two keys, "Set Variable" and "Insert
  Variable", that open dialogs instead of editing the expression.
- Set Variable asks for a name and a value. The value is not stored literally: it
  goes through the scientific engine first, in the angle mode currently in force,
  so `2 * pi` or another variable can be assigned. While the display rests on a
  number, a third button - "Use Result Number" - offers that number directly.
- The names come from one list in `config.py`: a set of physics symbols whose
  meaning is spelled out beside them in the picker ("μ — friction / coefficient of
  friction", "ρ — density", "λ — wavelength", and the rest), followed by every
  remaining single lower-case letter as a plain name. The picker is searchable.
- A value the engine rejects is reported inside the field and leaves the variable
  untouched; a name that is not on the list is reported the same way.
- Insert Variable offers only the variables that already have a value, each
  labelled `name = value`; with nothing set yet it says so instead of opening an
  empty list.
- Inserting appends the name to the expression, multiplying implicitly when the
  expression already ends on a number, a name or a closing bracket, and replacing
  the display outright when it rests on a result.
- A line under the display lists the variables currently set (`x = 3    F = 12`).
  It is shown only in scientific mode and only while at least one variable has a
  value.
- Variables live in the app for the session: they survive switching between the
  two calculators, and nothing is kept between runs.

## Calculation history

- Every `=` that produces an answer records the equation and the answer; the most
  recent `config.MAX_HISTORY_ITEMS` entries are kept and shown newest first.
- The history lives in its own drawer on the trailing edge of the window and
  carries a "Clear history" button.
- Each entry is a card as wide as the drawer, with the expression and the answer
  both being buttons: tapping the expression puts it back in the display for
  editing, tapping the answer appends it to the expression. Either closes the
  drawer afterwards.
- Each card carries a copy button for its answer (see "Copy to clipboard").

## App header

- The header row at the top of the window carries, left to right: a menu button
  that opens the navigation drawer, the "AnythingCalculator" title over a small
  muted caption, and a history button that opens the history drawer.
- That caption names what the content area is showing: "REGULAR MODE",
  "SCIENTIFIC MODE", "UNIT CONVERSION" or "PI CALCULATION". It is the same caption
  style the drawer heading uses.

## Copy to clipboard

- Every result the app produces carries a small copy button - an icon-only
  `CONTENT_COPY` button, not a full-width button.
- The one exception is a value far too long for anyone to select by hand: the
  decimals of a computed pi. There the button is a text button carrying the same
  `CONTENT_COPY` icon and a label that says out loud what it copies - "Copy all
  100,000 decimals" - and it hands over the whole of the value, however little of
  it happens to be on screen.
- The button copies the value as it is displayed at the moment of the click, so
  it never copies a stale value.
- Surfaces that must be copyable:
  - the calculator display (expression or result),
  - the answer of each calculation history entry,
  - the unit conversion result,
  - the result of a pi run on the Pi page,
  - the whole number in the Pi page's digits dialog, and the pi the program is
    currently calculating with.
- Use Flet's clipboard service (`ft.Clipboard`), with one service instance
  shared by the whole app rather than one per button.
- Confirm each copy with a snackbar showing the copied text, truncating long
  values.
- When a surface holds nothing, report that there is nothing to copy instead of
  writing an empty string to the clipboard.
- Do not offer error text for copying: the display's copy button is disabled
  while the display shows an error message.

## Pi calculation

- Offer a "Pi Calculation" page, reachable as its own drawer destination under an
  "Other" heading at the bottom of the drawer - below the Unit Conversions
  entries, since it is not a unit conversion. Give it the `SUPPORT` icon.
- Compute pi with the Chudnovsky algorithm and binary splitting
  (`src/pi.py`), not with `math.pi`: the app calculates its own digits. The
  series buys ~14.18 decimals a term, so a run has a known term count up front.
- Take the final square root ten decimals past the requested count and truncate
  back (`GUARD_DECIMALS`): an integer root is up to a unit short, which would
  otherwise make the last displayed decimal one too low for about one digit count
  in sixty (600 decimals is one of them). The series is already good for some
  twenty-eight decimals past the count, so the guard is free accuracy.
- Offer any digit count from 3 to 100 000 000: a menu of presets (3, 12, 100,
  1 000, 10 000, 100 000, 1 000 000, 10 000 000, 100 000 000) plus an exact
  field for a count between them (500 000, say). A count outside the range, or
  one that is not a whole number, disables the button and says why instead of
  starting a run.
- On start-up the app computes pi to 12 decimals and installs that as the
  program's pi. Every calculation in the app - both pads, the live preview,
  anything that reaches for `pi` - reads that one value (`pi.program_pi`) rather
  than `math.pi`; a test can hand the engine its own value through the
  `pi_provider` seam.
- The computed value is held two ways and both must agree: a `Decimal` for the
  engine to multiply by, and the decimals as a string for display. A run is only
  adopted when the digits spell exactly the value handed over, so a half-finished
  or corrupt run can never become what every calculation multiplies by.
- Until the app has computed its own pi it falls back on the expansion of the
  float `math.pi` - 15 decimals - and the digit count it reports says how accurate
  that really is, so nothing ever claims more digits than it holds.
- Pi is reachable in an expression under the ASCII name `pi` and under the Unicode
  pi codepoints as well: the Greek small pi (U+03C0), the Greek pi symbol (U+03D6),
  the double-struck small pi (U+213C) and the mathematical alphanumeric pi
  codepoints (bold, italic, bold-italic and sans-serif). Every alias resolves to
  the one program's pi, so an expression typed or pasted with any pi glyph still
  calculates. The mathematical forms need no per-style entry: Python normalizes
  identifiers to their base letter form, so a bold or sans-serif pi reaches the
  Greek small pi alias whatever the table lists.
- Computing pi needs no third-party library in the artifact: `src/pi.py` runs on
  plain Python integers. Where `gmpy2` is installed on the host it is used for
  `mpz` and the integer square root because it is faster; it is an optional
  extra (`[project.optional-dependencies] pi`, and pulled in by `dev` for the
  tests), never a runtime dependency, because it has no Android wheel and would
  break `flet build apk|aab`.
- `src/pi.py` additionally has a command-line entry - `python src/pi.py [digits]`
  - for computing a pi outside the app. It uses a `tqdm` bar when `tqdm` happens
  to be installed and runs without one when it is not; the app's page never uses
  either.
- Opening the Pi page again after a run shows what that run produced - the digits,
  the progress numbers and the typed digit count are held in the page's own
  controls and the control tree is reused, not rebuilt empty.
- The page shows two numbers of its own: the pi the program is calculating with at
  the top, as its leading decimals, and the finished run in a result card, again
  as a leading slice with an ellipsis when the run is longer than the card can
  hold. The whole number is only ever opened in the digits dialog.
- A run that fails for a reason other than being stopped says so on the page and
  leaves the buttons ready to try again; the program keeps the pi it already used.
- While a run is going show a progress bar with, under it, the percentage done,
  the term count, which part of the run is under way, the speed in digits per
  second and a time estimate (what is left and what the whole run is expected to
  take). Weigh the bar by work and not by terms: the products that combine the
  terms, and the final square root and division, outweigh the terms themselves and
  come after them, so a bar that counted terms alone reports the last term at well
  under two thirds of the wait and looks finished long before the run is. Name the
  phase - the split, the terms and their products, the last square root and
  division - so a bar that appears to stall says what the wait is busy with.
  Derive speed and estimate from the work done and the elapsed time, never from a
  guess, and cap how often a long run may report so checkpoints cannot cost more
  than the arithmetic between them.
- Repaint that card every half second while a run is going, whether or not the reader
  presses anything. One huge multiplication can hold a report back for a long stretch,
  and a bar that waits for reports stands still for exactly the longest part of the run.
  The painter is a task on the page's own event loop - not a second `run_thread`, whose
  executor is shared with every other handler in the app and can leave the painter queued
  behind them, which is what makes a bar look frozen until something else repaints the
  page. Pace it against a schedule rather than a chain of sleeps, because a loop sharing
  the interpreter with a computation over huge integers wakes late and chained sleeps add
  that lateness up.
- That painter must outlive a frame that fails to reach the client: one bad frame costs
  one frame, the clock keeps asking on schedule, and the card says what failed instead of
  going silent. A painter task that dies quietly is exactly the bar that looks frozen
  until the reader presses something and a handler repaints the page.
- The engine's checkpoints may ask for a paint as well - a checkpoint reached inside one
  huge multiplication is often the only progress the clock could show until the
  interpreter yields again - but the interval is held in the painter rather than in
  either caller, so clock ticks and reports spend one shared budget of two frames a
  second. A million reports must never become a million page updates: it is the same
  thread that has to stay free for the arithmetic.
- Once a run has ended the card belongs to the outcome: a late tick must never write a
  mid-run number over what a finished or cancelled run reports.
- Keep the unfilled part of the bar a different colour than the card it sits on; a
  track in the card's own colour leaves no whole to measure against and the bar
  reads as a growing blob.
- Run the computation on a worker thread - the pads must stay responsive - using
  Flet's own `page.run_thread` rather than a bare thread, and keep every repaint of
  the progress card inside the shared half-second budget above no matter how many
  terms the series reports. Offer a Stop
  button that is honoured wherever a run can be interrupted - at every node of the
  binary split and at each of the final square root, multiply and divide, and not
  only between terms, since a stop pressed during that tail otherwise goes
  unanswered until the run finishes. A cancelled run comes back with no digits,
  leaves the program's pi untouched and says how far the run got as a share of the
  whole and which phase it stopped in.
- Offer a "Use this value for the program" button that makes a finished run the
  pi every calculation uses; until it is pressed the run is only shown on the
  page. Show the pi currently in force at the top of the page so the effect is
  visible.
- Say out loud what the app's Decimal precision means for a pi the whole program
  uses: every calculation runs at `config.DECIMAL_PRECISION` significant digits,
  one of which is spent on the `3`, so a computed pi longer than that is stored and
  shown in full but only its first `DECIMAL_PRECISION - 1` decimals ever reach an
  answer. State it on the page and again where an adoption reports itself, or a
  hundred thousand adopted decimals looks like it changed nothing at all.
- Give every input on the page a row of its own that it can stretch across: two
  inputs sharing one row each take their own intrinsic width and together overflow
  the page, which on a phone leaves the second one off screen and unreachable.
- Viewing the digits opens a dialog that shows the number as plain text in an
  ordinary scroll area - digits and nothing else on a line, no line numbers, no
  monospace, no code-viewer styling. It holds one page of the number at a time -
  10 000 decimals - and turns pages when asked; a hundred million digits are never
  put on the screen at once, which is what would make the app lag or die. Lay the
  list out on a fixed line extent so the renderer only ever builds the lines inside
  the viewport, and never build a line past the end of the number.
- Never grow that list while the reader is scrolling it. A list that extends under
  their fingers keeps changing the very distance its scrollbar is measuring, so the
  thumb resizes mid-drag, the end keeps running away from them and the thumb ends up
  a meaningless sliver: a scrollbar can only be honest about a length that does not
  move. Nothing is added or removed while a page is being read.
- Give the dialog First / Previous / Next / Last buttons, disabled when there is
  nowhere left to go, and a footline saying which part of the number is on screen -
  "decimals 10 001 to 20 000 of 60 000 - page 2 of 6". A page turn replaces the lines
  rather than appending to them, starts again at the top of the page, keeps the last
  page short instead of padded, and cannot move past either end of the number. A
  number that fits one page has all four buttons disabled.
- Keep the scrollbar off the digits: hold a gutter at the right of the list and
  measure a line against what is left of it, so the thumb never sits on top of the
  digits it is supposed to be about.
- Measure how many decimals one line holds from the window the dialog opens on, so
  a narrow window gets a shorter line instead of a line whose tail is cut off, and
  never let a line run wider than the dialog.
- Give the dialog a button that says what it copies and copies every decimal of the
  run in one press, whatever part of the number happens to be on screen - selecting
  a hundred thousand digits by hand is not something a person can do.
- Keep the whole feature importable without Flet: the algorithm in `pi.py`, the
  run wrapper and the program's pi in `pi_value.py`, only the page in
  `pi_view.py`.
- Hold the digits to an outside opinion rather than to themselves: the engine
  tests check a run of 500 000 decimals - and one of 100 000 - against MPFR's own
  pi (`gmpy2.const_pi`), which reaches the digits by a different algorithm.
- A pi has no bridge to any unit group: no joule-to-newton or ccf-to-therm hop,
  and the conversion groups stay closed to it.

## Testing

### The host path: the default for every change

- Verify a change with the Flet tooling on the host and stop there: `flet run`
  starts the app to look at it, `flet test` runs the whole suite, and
  `flet test -k engine` the pure engine files (the fast check - 270 tests in
  about four seconds). The full suite is 342 tests and takes about eight minutes
  (340 pass and 2 are skipped; each UI test boots its own app host), so a
  `flet test` that runs for minutes is working, not hung. No emulator, device or
  APK is involved in this path, and it is what a change is judged by unless
  Android testing is asked for; the device route is the separate, opt-in path
  under "The Android emulator path: only when it is asked for".
- Run the suite with `flet test` (pytest flags only, no file paths - select with
  `-k`); the pure engine tests and the pi page tests (`test_pi_view.py`, which
  drives the page against a stub page) additionally run under plain `pytest`
  because they need no app host.
- Keep tests in a `tests/` folder at the workspace root, a sibling of `src/`:
  `src/` is what gets packaged into the app, test code stays on the host and
  drives the app from outside.
- Take test tooling from the `flet[cli,desktop,test]` extra inside the optional
  `dev` extra (it provides the `flet` command, the desktop run client, pytest,
  pytest-asyncio and the screenshot-comparison libraries); never add it to the
  runtime dependency set - the runtime set is what gets pip-installed into a
  packaged app, and only the Android-incompatible reason for that is enough.
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
- The drawer's entry list scrolls, and the test host has neither scroll nor drag,
  so a conversion group whose drawer entry falls below the host window height
  cannot be opened from a UI test at all. Skip such a page test with a reason
  rather than dropping it or reshuffling the groups, and leave the group covered by
  the conversion engine tests. Two page tests are skipped that way today: the Force
  Conversion entry, ninth in the list, and the Pi Calculation entry under "Other".
  The pi page is not left uncovered by that skip - `test_pi_view.py` drives the
  whole page, its progress card and its digits dialog against a stub page, and
  `test_pi_engine.py` covers the computation.
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

### The Android emulator path: only when it is asked for

- Take this path when testing on Android has been asked for - on-device, mobile or
  APK testing named by the user - and otherwise stay on the host path above. The
  emulator never replaces the host suite and no routine verification depends on it;
  it is the slow route (a cold boot plus an APK build), so do not reach for it
  uninvited. When it is asked for, work in this order: confirm the AVD is
  accelerated (KVM), boot it, build the APK, install and start it, then drive and
  read the running app from outside with `adb`.
- On-device smoke testing runs against an Android emulator, not a second desktop
  window: `flet emulators` lists and starts the virtual devices and
  `flet devices android` lists what is attached, which is what `flet build apk`
  and `flet run --android` then target. The installed debug APK is pushed with
  `adb install -r build/apk/anycalc.apk` and started with
  `adb shell am start -n com.github.greentruck50.anycalc/.MainActivity`; the
  emulator's Android SDK lives in `~/Android/Sdk` and its AVDs in
  `~/.android/avd`.
- Budget a device run honestly: `flet build apk` took about eight minutes from a
  cold cache and most of that is Gradle, so the Gradle and Kotlin compile daemons
  and the caches under `~/.gradle` are worth leaving alive between runs (`pgrep -f
  GradleDaemon` finds them) - a rebuild into warm daemons costs a few minutes
  instead. The AVD cold boot is the cheap part.
- To look at something transient - a ripple, an animation, an in-between frame -
  do not tap, hold the touch: `adb shell input motionevent DOWN x y` leaves the
  guest in the pressed state, `adb exec-out screencap -p > /tmp/press.png` catches
  the frame while it is held, and `adb shell input motionevent UP x y` completes
  the press. One capture then proves both halves of a press - the effect and the
  commit. `screencap` pixels map 1:1 onto `adb shell input` coordinates, and
  `adb shell wm size` gives the extent.
- A purely visual check of a running app is the one case the host path cannot
  cover: no synthetic input reaches the real desktop window from a Wayland session
  (X11 injectors such as xdotool cannot post events to Wayland clients, and are not
  installed here), and a host screenshot only catches whichever frame happens to
  be up plus the host's own windows on top. The emulator is fully scriptable
  through `adb`. For that kind of check, ask before taking the device run rather
  than assuming it.
- Keep an emulator usable for a GPU-composited app: the AVD defaults ship with the
  emulated GPU disabled, which the app feels as a crawl, so the AVD's
  `config.ini` must carry `hw.gpu.enabled=yes` with `hw.gpu.mode=host` (plus
  more cores/RAM than the 2-core, 1536 MB default). Check the host accelerator
  with `~/Android/Sdk/emulator/emulator-check accel` - it must report KVM usable,
  which needs read/write access to `/dev/kvm`.
- KVM being switched on is not proved by a process listing: check the fds the
  running emulator holds (`/dev/kvm`, `kvm-vm` and one `kvm-vcpu:N` per core) or
  ask it directly with `~/Android/Sdk/emulator/emulator-check accel`, which answers
  `KVM (version 12) is installed and usable`. Never read the launch line for this:
  emulators before 37 spelled the accelerator out as `-enable-kvm -smp cores=N -m MB`,
  while 37 puts only `-avd <name>` in `argv` and configures acceleration internally,
  so grepping the command line reports "no KVM" on a perfectly accelerated device.
- Keep the emulator component current rather than trusting the version the SDK
  bootstrap happened to download: `sdkmanager --list` compares what is installed
  with what the repository serves, and `sdkmanager "emulator"` installs the latter
  (the SDK here shipped 36.6.11 and now serves 37.2.12, build 16428233). Close the
  running device first with `adb -s emulator-5554 emu kill`, because replacing a
  binary that is in use fails, and boot the first run after an update cold with
  `-no-snapshot-load`, since a snapshot written by another emulator version is not
  reusable. A cold boot of this AVD completes in under a minute and a debug APK
  then starts in about 2 s (`am start -W` reporting `Status: ok, TotalTime: 2004`).
- An emulator window is an ordinary host window, so a host that saturates its CPU
  or disk makes the *emulator* stall and the desktop shell declare that window
  unresponsive. The liveness check is a `_NET_WM_PING` round-trip answered by
  the client's *event loop*, not its render path, so a window can keep drawing
  perfectly and still be called frozen - that message is not the app and no test
  result depends on it. Running the emulator with `-no-window` drops the X11
  client altogether - the only way to be unobservable to the desktop, and
  scripted captures still work through `adb exec-out screencap -p`.
  The shell blames one window rather than the program, and the emulator owns
  several: the device screen, the vertical button strip docked beside it (54 px wide,
  `_NET_WM_WINDOW_TYPE_UTILITY`) and Qt helper windows as small as 1x21 px - and every
  one of them advertises `_NET_WM_PING`. Because the "not responding" banner is drawn
  over the window that missed the ping, a victim that is 54 px or 1 px wide leaves the
  banner no room for a single readable letter; an unreadable sliver over the sidebar is
  the toolbar or a helper window being blamed, never the calculator. mutter's
  `check-alive-timeout` (`gsettings get org.gnome.mutter check-alive-timeout`, 5000 ms
  by default, `0` disables the check outright) is the only dial, and it is per desktop,
  not per window - no client can opt one of its windows out of the ping.
  Starve it less: keep `hw.cpu.ncore` below the host's core count instead of equal
  to it (3 of 4 cores here), launch the emulator without `-verbose`, which writes
  a debug line per rendered frame, and never run a full-disk scan next to a device
  run - the emulator lowers its own scheduling priority, so it is the first thing
  starved when the cores fill up. Launching it as
  `ionice -c2 -n7 taskset -c 0-2 <emulator> -avd anycalc ...` reserves a core for
  the desktop and makes it yield on disk I/O; wrapping it in `nice` is possible
  but makes the emulator itself, not the desktop, the thing that stalls first.
- Tell an app freeze from a host freeze by asking the guest, not the desktop:
  `adb logcat -d | grep -c "ANR in"` must stay at 0 and the app must hold focus
  (`dumpsys window` naming the app's `MainActivity` as `mCurrentFocus`), because a
  real Android "isn't responding" dialog always takes that focus away.
- Drive the running app from outside with `adb shell input tap x y` after reading
  the widget tree from `adb shell uiautomator dump`: the app exposes every keypad
  button as a clickable node carrying its label as the node description and the
  display as an editable text node, so taps and assertions can be scripted
  without the desktop test host.
- A device run is a debug-signed artifact, not a release one: it proves the app
  installs and renders on Android, and publishing still needs a real keystore.

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
  - `pi.py` - the pi computation itself (Chudnovsky + binary splitting), the
    digit counts the app offers and the one pi the program calculates with; it
    runs on stdlib integers, borrows `gmpy2` only when the host happens to have
    it, and doubles as a command-line tool;
  - `pi_value.py` - a pi run packaged for the page: timing, progress numbers and
    adopting a finished run;
  - `ui.py` - the app object: page setup, the display state (expression, result
    mode, DEG/RAD, named variables, history) and the navigation wiring;
  - `keypad.py` - which keys each pad shows and how a key looks;
  - `conversion_view.py` - the conversion form, its live re-conversion and its
    chain cards;
  - `pi_view.py` - the pi page: the digit choice, the progress card, adopting a
    run and the paged digits dialog;
  - `history_view.py` - the history cards and the history drawer;
  - `variable_dialogs.py` - the Set Variable / Insert Variable dialogs;
  - `clipboard.py` - the single clipboard service behind every copy button;
  - `styles.py` - the colour palette, so one hex value cannot drift between
    controls.
- The unit data sits with them as `src/assets/conversions.yaml`, addressed only
  through `config.CONVERSION_CONFIG_PATH` so the packaged artifact finds it.
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
  no `requirements.txt`. Runtime dependencies are `flet` and `PyYAML` only. The
  `cli`, `desktop` and `test` extras belong to the optional `dev` extra, because
  every build pip-installs `project.dependencies` **into the artifact** for its
  target platform: `flet-cli` pulls `watchdog`, which has no Android wheel, so
  keeping the extras in the runtime set makes `flet build apk|aab` fail with
  "No matching distribution found for watchdog". The `flet` command and the
  desktop run client are therefore host tooling and are never part of a shipped
  bundle; a desktop build ships its own runner from the Flutter app shell.
- The optional extras are `dev` (the `flet[cli,desktop,test]` extra plus `pytest`,
  `pytest-asyncio` and `gmpy2`, which the tests import directly), `pi` (`gmpy2`,
  the accelerator for `src/pi.py`) and `docs` (`mkdocs`). None of them is ever a
  runtime dependency for the reason above - `gmpy2` is a C extension with no
  Android wheel, exactly like `watchdog` - and each stays in its own extra so a CI
  job installs only what it needs.
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
  application/bundle id (`com.github.greentruck50.anycalc`) and the name the
  platform shows.
- The app id must be derived from the project's GitHub handle, never from a
  personal name, e-mail address or machine path. Nothing tracked may carry
  personal identifiers - no real name, e-mail, phone number or absolute path
  under a user's home directory; `~`-relative paths are fine.
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

## Documentation

- The prose documentation lives in `docs/` at the workspace root and is built by
  MkDocs from `mkdocs.yml` beside it. This file stays the requirements document:
  the docs describe what the app is, this file says what it must be.
- The hub is `docs/anycalc (Flet calculator app).md`, with a source-layout page, a
  testing page, and `docs/Change log & decisions.md`, which records each change
  with the reasoning behind it - including the dead ends, which is what keeps the
  same mistake from being made twice.
- Those notes were kept in Trillium notes before being migrated into `docs/`;
  `DOCUMENTATION_REMINDER.txt` is the reminder that they live here now.
- `mkdocs build` writes `site/`, which is gitignored and never committed: it
  mirrors every word of `docs/`, so a tracked copy only duplicates the repository.
- `.github/workflows/docs.yml` rebuilds and publishes `docs/` to GitHub Pages on
  any push to `main` touching `docs/**`, `mkdocs.yml` or the workflow itself, and
  builds with `mkdocs build --strict`, so a broken internal link fails the deploy
  instead of shipping. That job installs only the `[docs]` extra.
- The documentation carries no personal data either: the project is named by its
  GitHub handle (`GreenTruck50/anycalc` in `mkdocs.yml`), never by a real name, an
  e-mail address or a path under someone's home directory.

