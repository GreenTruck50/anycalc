"""Engine tests - no window, no app, just the arithmetic.

``src/conversions.py`` imports cleanly, so these tests load ``src/assets/conversions.yaml``
and drive the conversion graph and the Decimal arithmetic straight in the host
process. They are the cheap half of the suite; ``tests/test_app.py`` drives the
same code through the real built app.

The exactness sweep is the load-bearing test. Every unit in the Volume, Area,
Weight, Energy and Force groups is defined by law (NIST Handbook 44, the 1959
international yard-and-pound agreement, the International Table calorie and
Btu, standard gravity, the 2019 SI), so each pair's factor is an exact rational
number. Whenever that rational has a terminating decimal expansion, the value
the app produces must be *bit for bit* that decimal - which is what catches a
factor that somebody typed in rounded, or a hop that divides where it should
multiply. The Length group gets its own, narrower sweep: a parsec is 648000/pi
astronomical units, so the parsec family has no rational metre to be measured
against and is left out. The same single exception exists in Energy - the
thermochemical Btu carries a 5/9, so it never ends as a decimal and gets its
own test instead.
"""

import itertools
from decimal import Decimal
from fractions import Fraction

import pytest

# _evaluate_conversion_formula is private, but the chain test needs the exact
# runner the app uses - re-implementing it here would test the test instead.
from conversions import (
    _evaluate_conversion_formula as evaluate,
    convert_units,
    find_conversion_path,
    format_conversion_value,
    load_conversion_config,
)

UNIT_GROUPS, CONVERSIONS = load_conversion_config()
UNITS_BY_GROUP = {group["name"]: group["units"] for group in UNIT_GROUPS}
CONVERSION_BY_NAME = {item["name"]: item for item in CONVERSIONS}
CONVERSION_NAMES = sorted(CONVERSION_BY_NAME)

F = Fraction

# Exact legal anchors, as rationals, so no float ever touches the truth table.
INCH3_ML = F(16387064, 10**6)          # 1 in³ in mL (= cm³), exact by definition
IN_M = F(254, 10000)                  # 1 in = 25.4 mm exactly (1959 agreement)
IN2_M2 = IN_M * IN_M                  # 1 in² = 0.00064516 m² exactly
US_GALLON_ML = 231 * INCH3_ML          # US liquid gallon = 231 in³
US_DRY_GALLON_ML = F(2688025, 10**4) * INCH3_ML   # US dry gallon = 2688025 in³ / 10^4
IMP_GALLON_ML = F(454609, 100)         # imperial gallon = 4.54609 L exactly
POUND_G = F(45359237, 10**5)         # 1 lb = 453.59237 g exactly
GRAIN_G = F(6479891, 10**8)          # 1 gr = 64.79891 mg exactly
POUND_KG = F(45359237, 10**8)        # 1 lb = 0.45359237 kg exactly (1959 agreement)
FOOT_M = F(3048, 10**4)              # 1 ft = 304.8 mm exactly (1959 agreement)
GRAVITY = F(980665, 10**5)           # standard gravity: 9.80665 m/s2 by definition
LBF_N = POUND_KG * GRAVITY           # 1 lbf = 4.4482216152605 N exactly
POUNDAL_N = POUND_KG * FOOT_M        # 1 pdl = 0.138254954376 N exactly
FOOT_POUND_FORCE_J = LBF_N * FOOT_M  # 1 ft-lbf = 1.3558179483314004 J exactly
CALORIE_IT_J = F(41868, 10**4)       # 1 cal (IT) = 4.1868 J exactly
CALORIE_TH_J = F(4184, 1000)         # 1 cal (th) = 4.184 J exactly
CALORIE_15_J = F(41855, 10**4)       # 1 cal (15 C) = 4.1855 J exactly
BTU_IT_J = F(105505585262, 10**8)    # 1 Btu (IT) = 1055.05585262 J exactly
BTU_TH_J = POUND_G * F(5, 9) * CALORIE_TH_J   # 1054.350264488... J - repeating

# Volume factors keyed by unit id, in millilitres (= cubic centimetres).
VOLUME_ML = {
    "volume_cubic_millimeter": F(1, 1000),
    "volume_cubic_centimeter": F(1),
    "volume_cubic_decimeter": F(1000),
    "volume_cubic_meter": F(10**6),
    "volume_cubic_kilometer": F(10**15),
    "volume_microliter": F(1, 1000),
    "volume_milliliter": F(1),
    "volume_centiliter": F(10),
    "volume_deciliter": F(100),
    "volume_liter": F(1000),
    "volume_hectoliter": F(10**5),
    "volume_kiloliter": F(10**6),
    "volume_metric_teaspoon": F(5),
    "volume_metric_tablespoon": F(15),
    "volume_australian_tablespoon": F(20),
    "volume_dessert_spoon": F(10),
    "volume_metric_cup": F(250),
    "volume_us_legal_cup": F(240),
    "volume_cubic_inch": INCH3_ML,
    "volume_cubic_foot": 1728 * INCH3_ML,
    "volume_ccf": 100 * 1728 * INCH3_ML,          # 1 ccf = 100 ft³ exactly
    "volume_cubic_yard": 27 * 1728 * INCH3_ML,
    "volume_cubic_mile": F(1760**3) * 27 * 1728 * INCH3_ML,
    "volume_acre_foot": F(43560 * 1728) * INCH3_ML,   # 1 acre-foot = 43560 ft³
    "volume_us_teaspoon": US_GALLON_ML / 768,
    "volume_us_tablespoon": US_GALLON_ML / 256,
    "volume_us_fluid_ounce": US_GALLON_ML / 128,
    "volume_us_gill": US_GALLON_ML / 32,
    "volume_us_cup": US_GALLON_ML / 16,
    "volume_us_pint": US_GALLON_ML / 8,
    "volume_us_quart": US_GALLON_ML / 4,
    "volume_us_gallon": US_GALLON_ML,
    "volume_petroleum_barrel": 42 * US_GALLON_ML,
    "volume_us_dry_pint": US_DRY_GALLON_ML / 8,
    "volume_us_dry_quart": US_DRY_GALLON_ML / 4,
    "volume_us_dry_gallon": US_DRY_GALLON_ML,
    "volume_imperial_fluid_dram": IMP_GALLON_ML / 1280,
    "volume_imperial_fluid_ounce": IMP_GALLON_ML / 160,
    "volume_imperial_gill": IMP_GALLON_ML / 32,
    "volume_imperial_pint": IMP_GALLON_ML / 8,
    "volume_imperial_quart": IMP_GALLON_ML / 4,
    "volume_imperial_gallon": IMP_GALLON_ML,
}

# Weight factors keyed by unit id, in grams.
WEIGHT_G = {
    "weight_microgram": F(1, 10**6),
    "weight_milligram": F(1, 1000),
    "weight_gram": F(1),
    "weight_kilogram": F(1000),
    "weight_tonne": F(10**6),
    "weight_quintal": F(10**5),
    "weight_carat": F(1, 5),
    "weight_grain": GRAIN_G,
    "weight_dram": POUND_G / 256,
    "weight_ounce": POUND_G / 16,
    "weight_pound": POUND_G,
    "weight_stone": 14 * POUND_G,
    "weight_hundredweight_short": 100 * POUND_G,
    "weight_hundredweight_long": 112 * POUND_G,
    "weight_short_ton": 2000 * POUND_G,
    "weight_long_ton": 2240 * POUND_G,
    "weight_pennyweight": 24 * GRAIN_G,
    "weight_troy_ounce": 480 * GRAIN_G,
    "weight_troy_pound": 5760 * GRAIN_G,
    "weight_scruple": 20 * GRAIN_G,
    "weight_apothecaries_dram": 60 * GRAIN_G,
    "weight_apothecaries_ounce": 480 * GRAIN_G,
    "weight_apothecaries_pound": 5760 * GRAIN_G,
}


# Area factors keyed by unit id, in square metres. The customary ones are all
# derived from the one square inch, and the land measures from the square yard,
# so the whole table is exact rationals of the same anchor.
AREA_M2 = {
    "area_square_micrometer": F(1, 10**12),
    "area_square_millimeter": F(1, 10**6),
    "area_square_centimeter": F(1, 10**4),
    "area_square_decimeter": F(1, 100),
    "area_square_meter": F(1),
    "area_square_kilometer": F(10**6),
    "area_are": F(100),
    "area_hectare": F(10**4),
    "area_square_inch": IN2_M2,
    "area_square_foot": 144 * IN2_M2,
    "area_square_yard": 1296 * IN2_M2,
    # 1 mi = 63360 in exactly, so a square mile is 63360 squared square inches
    "area_square_mile": F(63360**2) * IN2_M2,
    "area_acre": F(4840 * 1296) * IN2_M2,
    "area_rood": F(4840 * 1296) * IN2_M2 / 4,
    "area_square_rod": F(4840 * 1296) * IN2_M2 / 160,
}

# Energy factors keyed by unit id, in joules. Every one of them is a defined
# constant - the SI prefixes, the three legal calories, the International Table
# Btu, the exact 2019 electronvolt - so the whole table is exact rationals. The
# single exception is the thermochemical Btu: its 5/9 leaves a repeating decimal,
# so the YAML can only carry a rounded literal and this entry is the truth the
# rounded factor is measured against (see the test named after it).
ENERGY_J = {
    "energy_joule": F(1),
    "energy_kilojoule": F(1000),
    "energy_megajoule": F(10**6),
    "energy_gigajoule": F(10**9),
    "energy_erg": F(1, 10**7),
    "energy_calorie_it": CALORIE_IT_J,
    "energy_kilocalorie_it": 1000 * CALORIE_IT_J,
    "energy_calorie_th": CALORIE_TH_J,
    "energy_calorie_15": CALORIE_15_J,
    "energy_watt_hour": F(3600),
    "energy_kilowatt_hour": F(36 * 10**5),
    "energy_megawatt_hour": F(36 * 10**8),
    "energy_btu_it": BTU_IT_J,
    "energy_btu_th": BTU_TH_J,
    "energy_therm": F(100000) * BTU_IT_J,
    "energy_quad": F(10**15) * BTU_IT_J,
    "energy_horsepower_hour": F(1980000) * FOOT_POUND_FORCE_J,
    "energy_foot_pound_force": FOOT_POUND_FORCE_J,
    "energy_electronvolt": F(1602176634, 10**28),
}

# Force factors keyed by unit id, in newton. The gravitational metric units hang
# off standard gravity (exactly 9.80665 m/s2) and the imperial ones off the 1959
# pound, so both bridges are exact decimals rather than rounded ones.
FORCE_N = {
    "force_newton": F(1),
    "force_kilonewton": F(1000),
    "force_meganewton": F(10**6),
    "force_dyne": F(1, 10**5),
    "force_kilogram_force": GRAVITY,
    "force_gram_force": GRAVITY / 1000,
    "force_tonne_force": GRAVITY * 1000,
    "force_pound_force": LBF_N,
    "force_ounce_force": LBF_N / 16,
    "force_poundal": POUNDAL_N,
    "force_short_ton_force": F(2000) * LBF_N,
    "force_long_ton_force": F(2240) * LBF_N,
    "force_kip": F(1000) * LBF_N,
}


def unit_ids(conversion_name: str) -> list[str]:
    """Unit ids of the unit group that backs a conversion menu entry."""

    group_name = conversion_name.removesuffix(" Conversion")
    return [unit["id"] for unit in UNITS_BY_GROUP[group_name]]


def terminating_decimal(factor: Fraction, max_digits: int = 45) -> str | None:
    """Exact decimal of a rational factor, or None if it repeats or is huge.

    Values longer than ``max_digits`` are left to :func:`test_long_factors_keep_
    significant_digits`, because the engine works at 50 significant digits and
    the last couple of digits of a 45+ digit answer legitimately get rounded.
    """

    denominator = factor.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    if denominator != 1:
        return None

    exact = format(Decimal(factor.numerator) / Decimal(factor.denominator), "f")
    digits = len(exact.replace("-", "").replace(".", "").lstrip("0"))
    return exact if digits <= max_digits else None


def app_value(conversion_name: str, amount: str, source: str, target: str) -> Decimal:
    return convert_units(
        CONVERSION_BY_NAME[conversion_name], Decimal(amount), source, target
    ).value


# --- configuration -----------------------------------------------------------

def test_conversion_groups_are_the_expected_nine() -> None:
    assert set(CONVERSION_NAMES) == {
        "Length Conversion",
        "Time Conversion",
        "Temperature Conversion",
        "Data Conversion",
        "Volume Conversion",
        "Area Conversion",
        "Weight Conversion",
        "Energy Conversion",
        "Force Conversion",
    }


@pytest.mark.parametrize("conversion_name", CONVERSION_NAMES)
def test_group_has_exactly_its_own_units(conversion_name: str) -> None:
    """Every formula endpoint belongs to the group's own unit list."""

    ids = set(unit_ids(conversion_name))
    endpoints = {
        neighbour
        for formula in CONVERSION_BY_NAME[conversion_name]["formulas"].values()
        for neighbour in (formula["input_unit_id"], formula["output_unit_id"])
    }
    assert endpoints <= ids
    # No unit is orphaned: each one is wired into at least one formula.
    assert endpoints == ids


@pytest.mark.parametrize("conversion_name", CONVERSION_NAMES)
def test_every_pair_of_units_is_reachable(conversion_name: str) -> None:
    conversion = CONVERSION_BY_NAME[conversion_name]
    unreachable = [
        f"{source} -> {target}"
        for source, target in itertools.product(unit_ids(conversion_name), repeat=2)
        if find_conversion_path(conversion, source, target) is None
    ]
    assert unreachable == []


# --- exactness ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("conversion_name", "legal_factors", "minimum_pairs"),
    [
        ("Volume Conversion", VOLUME_ML, 700),
        ("Area Conversion", AREA_M2, 130),
        ("Weight Conversion", WEIGHT_G, 200),
        ("Energy Conversion", ENERGY_J, 100),
        ("Force Conversion", FORCE_N, 80),
    ],
    ids=["volume", "area", "weight", "energy", "force"],
)
def test_every_terminating_factor_is_exact(
    conversion_name: str, legal_factors: dict[str, Fraction], minimum_pairs: int
) -> None:
    """Each pair's factor must equal the legally defined rational exactly.

    Pairs whose true factor is a repeating decimal (imperial -> US, most troy
    -> metric) are skipped: the engine's 50-digit rounding is legitimate there.
    """

    ids = unit_ids(conversion_name)
    assert sorted(ids) == sorted(legal_factors), (
        f"{conversion_name} units and the test's legal table drifted apart: "
        f"{set(ids) ^ set(legal_factors)}"
    )

    checked = 0
    wrong: list[str] = []
    for source, target in itertools.permutations(ids, 2):
        want = terminating_decimal(legal_factors[source] / legal_factors[target])
        if want is None:
            continue
        checked += 1
        got = format_conversion_value(app_value(conversion_name, "1", source, target))
        if Decimal(got) != Decimal(want):
            wrong.append(f"{source} -> {target}: app {got}, exact {want}")

    assert checked >= minimum_pairs, f"only {checked} comparable pairs - too few"
    assert wrong == [], (
        f"{len(wrong)} of {checked} pairs are not exact:\n" + "\n".join(wrong[:20])
    )


def test_long_factors_keep_significant_digits() -> None:
    """A cubic mile in cubic centimetres is a 37-digit number.

    The engine parses formula literals through ``Decimal(str(float))``, which
    truncates anything past ~15 significant digits, so a factor written as one
    long decimal literal silently loses precision. The YAML chains integer
    multipliers instead, so the answer must still match the exact rational far
    beyond what a float could carry.
    """

    exact_cm3_to_mi3 = 1 / (F(1760**3) * 27 * 1728 * INCH3_ML)
    got = app_value(
        "Volume Conversion", "1", "volume_cubic_centimeter", "volume_cubic_mile"
    )
    relative_error = abs(Fraction(got) - exact_cm3_to_mi3) / exact_cm3_to_mi3
    assert relative_error < F(1, 10**30), f"{got} is off by {float(relative_error):.2e}"


# --- numbers a shop, a lab or a court would recognise -----------------------

REFERENCE_VALUES = [
    # (conversion, from, to, amount, exact answer as shown in the app)
    # Volume - metric
    ("Volume", "volume_cubic_centimeter", "volume_milliliter", "1", "1"),
    ("Volume", "volume_liter", "volume_milliliter", "1", "1000"),
    ("Volume", "volume_hectoliter", "volume_liter", "1", "100"),
    ("Volume", "volume_kiloliter", "volume_liter", "2", "2000"),
    ("Volume", "volume_microliter", "volume_milliliter", "1", "0.001"),
    ("Volume", "volume_cubic_meter", "volume_liter", "1", "1000"),
    ("Volume", "volume_cubic_kilometer", "volume_cubic_meter", "1", "1000000000"),
    # Volume - US customary / legal
    ("Volume", "volume_us_gallon", "volume_cubic_inch", "1", "231"),
    ("Volume", "volume_us_gallon", "volume_us_fluid_ounce", "1", "128"),
    ("Volume", "volume_us_fluid_ounce", "volume_milliliter", "1", "29.5735295625"),
    ("Volume", "volume_us_tablespoon", "volume_milliliter", "1", "14.78676478125"),
    ("Volume", "volume_us_teaspoon", "volume_milliliter", "1", "4.92892159375"),
    ("Volume", "volume_us_tablespoon", "volume_us_teaspoon", "1", "3"),
    ("Volume", "volume_us_pint", "volume_us_fluid_ounce", "1", "16"),
    ("Volume", "volume_us_gill", "volume_us_fluid_ounce", "1", "4"),
    ("Volume", "volume_petroleum_barrel", "volume_us_gallon", "1", "42"),
    ("Volume", "volume_us_legal_cup", "volume_milliliter", "1", "240"),
    ("Volume", "volume_us_dry_gallon", "volume_us_dry_pint", "1", "8"),
    # Volume - imperial & metric kitchen
    ("Volume", "volume_imperial_gallon", "volume_liter", "1", "4.54609"),
    ("Volume", "volume_imperial_gallon", "volume_imperial_fluid_dram", "1", "1280"),
    ("Volume", "volume_imperial_fluid_ounce", "volume_milliliter", "1", "28.4130625"),
    ("Volume", "volume_imperial_pint", "volume_imperial_gill", "1", "4"),
    ("Volume", "volume_metric_cup", "volume_metric_teaspoon", "1", "50"),
    # Volume - survey / dry
    ("Volume", "volume_cubic_foot", "volume_cubic_inch", "1", "1728"),
    ("Volume", "volume_cubic_yard", "volume_cubic_foot", "1", "27"),
    ("Volume", "volume_cubic_foot", "volume_cubic_centimeter", "1", "28316.846592"),
    ("Volume", "volume_acre_foot", "volume_cubic_foot", "1", "43560"),
    # Volume - the gas trade measure (1 ccf = 100 ft3)
    ("Volume", "volume_ccf", "volume_cubic_foot", "1", "100"),
    ("Volume", "volume_ccf", "volume_cubic_inch", "1", "172800"),
    ("Volume", "volume_ccf", "volume_cubic_centimeter", "1", "2831684.6592"),
    ("Volume", "volume_ccf", "volume_liter", "1", "2831.6846592"),
    # Area - metric and metric land
    ("Area", "area_square_meter", "area_square_centimeter", "1", "10000"),
    ("Area", "area_square_kilometer", "area_square_meter", "1", "1000000"),
    ("Area", "area_square_micrometer", "area_square_millimeter", "1", "0.000001"),
    ("Area", "area_hectare", "area_are", "1", "100"),
    ("Area", "area_hectare", "area_square_meter", "1", "10000"),
    # Area - customary and customary land
    ("Area", "area_square_foot", "area_square_inch", "1", "144"),
    ("Area", "area_square_yard", "area_square_foot", "1", "9"),
    ("Area", "area_square_mile", "area_acre", "1", "640"),
    ("Area", "area_acre", "area_square_rod", "1", "160"),
    ("Area", "area_square_rod", "area_square_yard", "1", "30.25"),
    # Area - across the 1 in2 = 0.00064516 m2 bridge
    ("Area", "area_square_inch", "area_square_centimeter", "1", "6.4516"),
    ("Area", "area_acre", "area_square_foot", "1", "43560"),
    ("Area", "area_acre", "area_square_meter", "1", "4046.8564224"),
    ("Area", "area_acre", "area_hectare", "1", "0.40468564224"),
    # Weight - avoirdupois
    ("Weight", "weight_pound", "weight_gram", "1", "453.59237"),
    ("Weight", "weight_ounce", "weight_grain", "1", "437.5"),
    ("Weight", "weight_dram", "weight_grain", "1", "27.34375"),
    ("Weight", "weight_pound", "weight_ounce", "1", "16"),
    ("Weight", "weight_stone", "weight_pound", "1", "14"),
    ("Weight", "weight_short_ton", "weight_pound", "1", "2000"),
    ("Weight", "weight_long_ton", "weight_hundredweight_long", "1", "20"),
    # Weight - metric, apothecaries, troy
    ("Weight", "weight_grain", "weight_milligram", "1", "64.79891"),
    ("Weight", "weight_carat", "weight_milligram", "1", "200"),
    ("Weight", "weight_tonne", "weight_kilogram", "1", "1000"),
    ("Weight", "weight_quintal", "weight_kilogram", "1", "100"),
    ("Weight", "weight_kilogram", "weight_microgram", "1", "1000000000"),
    ("Weight", "weight_troy_pound", "weight_pennyweight", "1", "240"),
    ("Weight", "weight_troy_ounce", "weight_pennyweight", "1", "20"),
    ("Weight", "weight_pennyweight", "weight_grain", "1", "24"),
    ("Weight", "weight_apothecaries_pound", "weight_scruple", "1", "288"),
    ("Weight", "weight_apothecaries_dram", "weight_grain", "1", "60"),
    # Energy - metric, electrical and the exact calories
    ("Energy", "energy_kilowatt_hour", "energy_joule", "1", "3600000"),
    ("Energy", "energy_megajoule", "energy_kilojoule", "1", "1000"),
    ("Energy", "energy_erg", "energy_joule", "1", "0.0000001"),
    ("Energy", "energy_calorie_it", "energy_joule", "1", "4.1868"),
    ("Energy", "energy_kilocalorie_it", "energy_kilojoule", "1", "4.1868"),
    ("Energy", "energy_calorie_th", "energy_joule", "1", "4.184"),
    ("Energy", "energy_calorie_15", "energy_joule", "1", "4.1855"),
    ("Energy", "energy_watt_hour", "energy_kilowatt_hour", "1", "0.001"),
    # Energy - the BTU family and the mechanical units
    ("Energy", "energy_btu_it", "energy_joule", "1", "1055.05585262"),
    ("Energy", "energy_therm", "energy_btu_it", "1", "100000"),
    ("Energy", "energy_therm", "energy_joule", "1", "105505585.262"),
    ("Energy", "energy_quad", "energy_btu_it", "1", "1000000000000000"),
    ("Energy", "energy_foot_pound_force", "energy_joule", "1", "1.3558179483314004"),
    ("Energy", "energy_horsepower_hour", "energy_foot_pound_force", "1", "1980000"),
    (
        "Energy",
        "energy_electronvolt",
        "energy_joule",
        "1",
        "0.0000000000000000001602176634",
    ),
    # Force - metric and gravitational metric
    ("Force", "force_kilonewton", "force_newton", "1", "1000"),
    ("Force", "force_dyne", "force_newton", "1", "0.00001"),
    ("Force", "force_kilogram_force", "force_newton", "1", "9.80665"),
    ("Force", "force_gram_force", "force_newton", "1", "0.00980665"),
    ("Force", "force_tonne_force", "force_kilonewton", "1", "9.80665"),
    # Force - imperial / US customary
    ("Force", "force_pound_force", "force_newton", "1", "4.4482216152605"),
    ("Force", "force_poundal", "force_newton", "1", "0.138254954376"),
    ("Force", "force_ounce_force", "force_pound_force", "1", "0.0625"),
    ("Force", "force_kip", "force_pound_force", "1", "1000"),
    ("Force", "force_long_ton_force", "force_pound_force", "1", "2240"),
    ("Force", "force_short_ton_force", "force_pound_force", "1", "2000"),
    # Groups that shipped before Volume / Weight - kept honest by the same tests
    ("Length", "length_mile", "length_yard", "1", "1760"),
    ("Length", "length_inch", "length_millimeter", "1", "25.4"),
    ("Length", "length_foot", "length_millimeter", "1", "304.8"),
    ("Length", "length_mile", "length_meter", "1", "1609.344"),
    ("Length", "length_mile", "length_kilometer", "1", "1.609344"),
    ("Length", "length_nautical_mile", "length_meter", "1", "1852"),
    ("Length", "length_astronomical_unit", "length_meter", "1", "149597870700"),
    ("Length", "length_light_year", "length_kilometer", "1", "9460730472580.8"),
    ("Time", "time_day", "time_second", "1", "86400"),
    ("Data", "data_gibibyte", "data_byte", "1", "1073741824"),
    ("Temperature", "temperature_celsius", "temperature_fahrenheit", "100", "212"),
    ("Temperature", "temperature_fahrenheit", "temperature_celsius", "32", "0"),
    ("Temperature", "temperature_celsius", "temperature_kelvin", "0", "273.15"),
    ("Temperature", "temperature_kelvin", "temperature_celsius", "273.15", "0"),
    ("Temperature", "temperature_celsius", "temperature_rankine", "0", "491.67"),
    ("Temperature", "temperature_fahrenheit", "temperature_rankine", "-40", "419.67"),
]


@pytest.mark.parametrize(
    "conversion,source,target,amount,want",
    REFERENCE_VALUES,
    ids=[f"{s}>{t}" for _, s, t, _, _ in REFERENCE_VALUES],
)
def test_reference_conversion(
    conversion: str, source: str, target: str, amount: str, want: str
) -> None:
    got = format_conversion_value(
        app_value(f"{conversion} Conversion", amount, source, target)
    )
    assert got == want


# --- the chain shown under the result ---------------------------------------

def test_chain_hops_join_up_and_reproduce_their_own_numbers() -> None:
    """What the chain card prints must be the arithmetic that was applied.

    A US liquid gallon to an imperial fluid dram has no direct formula, so the
    engine has to walk through several hops - and every hop it reports has to
    line up with the next one and re-evaluate to its own printed output.
    """

    outcome = convert_units(
        CONVERSION_BY_NAME["Volume Conversion"],
        Decimal("1"),
        "volume_us_gallon",
        "volume_imperial_fluid_dram",
    )
    hops = [(step.from_unit_id, step.to_unit_id) for step in outcome.steps]
    assert len(hops) >= 2, "expected a multi-hop chain between the two systems"
    assert hops[0][0] == "volume_us_gallon"
    assert hops[-1][1] == "volume_imperial_fluid_dram"
    assert all(left[1] == right[0] for left, right in zip(hops, hops[1:]))
    assert len(set(hops)) == len(hops), "a unit is visited twice"

    running = Decimal("1")
    for step in outcome.steps:
        assert step.applied_formula
        # _evaluate_conversion_formula is the app's own formula runner.
        assert evaluate(step.applied_formula, step.input_value) == step.output_value
        assert step.input_value == running
        running = step.output_value
    assert running == outcome.value


def test_reused_formula_is_reported_flipped() -> None:
    """A hop walked backwards must show the flipped formula, not the stored one.

    The YAML only defines tablespoons -> teaspoons ("x * 3"); converting the
    other way has to display "x / 3", because that is what actually ran.
    """

    outcome = convert_units(
        CONVERSION_BY_NAME["Volume Conversion"],
        Decimal("24"),
        "volume_us_teaspoon",
        "volume_us_tablespoon",
    )
    step, = outcome.steps
    assert step.used_backwards is True
    assert step.formula == "x * 3"
    assert step.applied_formula == "x / 3"
    assert format_conversion_value(outcome.value) == "8"


def test_same_unit_conversion_is_a_pass_through() -> None:
    outcome = convert_units(
        CONVERSION_BY_NAME["Volume Conversion"],
        Decimal("123.45"),
        "volume_liter",
        "volume_liter",
    )
    assert outcome.steps == []
    assert outcome.value == Decimal("123.45")


def test_groups_do_not_bleed_into_each_other() -> None:
    """Cross-group pairs stay an error - Volume has no bridge to Length."""

    with pytest.raises(ValueError, match="No conversion path"):
        convert_units(
            CONVERSION_BY_NAME["Volume Conversion"],
            Decimal("1"),
            "volume_liter",
            "length_meter",
        )


# --- the group that shipped before the exactness rule ------------------------

# Exact definitions of the Length units, in metres: the SI prefixes, the 1959
# yard-and-pound anchors (1 in = 25.4 mm, so 1 mi = 1609.344 m), the nautical
# mile at exactly 1852 m, and the IAU resolutions (1 AU = 149597870700 m, and a
# light-year, c over a Julian year, at exactly 9460730472580800 m).
INCH_M = F(254, 10000)
LENGTH_M = {
    "length_nanometer": F(1, 10**9),
    "length_micrometer": F(1, 10**6),
    "length_millimeter": F(1, 10**3),
    "length_centimeter": F(1, 100),
    "length_meter": F(1),
    "length_kilometer": F(1000),
    "length_terameter": F(10**12),
    "length_inch": INCH_M,
    "length_foot": 12 * INCH_M,
    "length_yard": 36 * INCH_M,
    "length_mile": 63360 * INCH_M,
    "length_nautical_mile": F(1852),
    "length_astronomical_unit": F(149597870700),
    "length_light_year": F(9460730472580800),
}

# A parsec is 648000/pi astronomical units, so a parsec - and every multiple of
# it - is not a rational number of metres and has no terminating factor to be
# exact about. They stay in the group, and in the reachability test, only here.
IRRATIONAL_LENGTH_UNITS = {
    "length_parsec",
    "length_kiloparsec",
    "length_megaparsec",
    "length_gigaparsec",
}


def test_length_group_uses_exact_legal_lengths() -> None:
    """The Length group is held to the same standard as Volume and Weight.

    It used to route the imperial units through rounded literals - "meter -> inch"
    was "x * 39.37007874" and "mile -> nautical mile" was "x / 1.150779448" - so
    inch -> millimetre came out as 25.4000000000000000000000000000...1 and
    nautical mile -> metre as 1851.9999994.... The exact anchors are in the YAML
    now, so every terminating Length factor has to be bit for bit right.
    """

    ids = [
        unit
        for unit in unit_ids("Length Conversion")
        if unit not in IRRATIONAL_LENGTH_UNITS
    ]
    assert sorted(ids) == sorted(LENGTH_M), (
        "the Length units and the test's exact table drifted apart: "
        f"{set(ids) ^ set(LENGTH_M)}"
    )

    checked = 0
    wrong: list[str] = []
    for source, target in itertools.permutations(ids, 2):
        want = terminating_decimal(LENGTH_M[source] / LENGTH_M[target])
        if want is None:
            continue
        checked += 1
        got = format_conversion_value(
            app_value("Length Conversion", "1", source, target)
        )
        if Decimal(got) != Decimal(want):
            wrong.append(f"{source} -> {target}: app {got}, exact {want}")

    assert checked >= 90, f"only {checked} comparable pairs - too few"
    assert wrong == [], (
        f"{len(wrong)} of {checked} pairs are not exact:\n" + "\n".join(wrong[:20])
    )


def test_the_irrational_parsec_hop_keeps_its_significant_digits() -> None:
    """A parsec cannot be written exactly, but it must not lose digits either."""

    # IAU 2015 resolution B3: 1 pc = 648000/pi astronomical units.
    pi = F(Decimal("3.141592653589793238462643383279502884197"))
    parsec_ly = (F(149597870700) * F(648000) / pi) / F(9460730472580800)

    got = app_value("Length Conversion", "1", "length_parsec", "length_light_year")
    relative_error = abs(Fraction(got) - parsec_ly) / parsec_ly
    assert relative_error < F(1, 10**13), f"{got} is off by {float(relative_error):.2e}"

# --- the one Energy factor that cannot be written exactly ---------------------


def test_the_rounded_thermochemical_btu_keeps_its_significant_digits() -> None:
    """The Btu (th) has no exact decimal, but it must not lose digits either.

    The International Table Btu is defined as exactly 1055.05585262 J, so it is
    exact like every other Energy unit. The thermochemical Btu is instead the
    heat for a pound of water per degree Fahrenheit - 453.59237 g x 5/9 x
    4.184 J - and that 5/9 leaves a repeating decimal. The YAML carries a 15
    significant digit literal, the most the engine can parse, so the answer is
    only as good as that literal; this pins how good it has to be.
    """

    got = app_value("Energy Conversion", "1", "energy_btu_th", "energy_joule")
    relative_error = abs(Fraction(got) - BTU_TH_J) / BTU_TH_J
    assert relative_error < F(1, 10**12), f"{got} is off by {float(relative_error):.2e}"


def test_the_multi_literal_foot_pound_hop_stays_exact_both_ways() -> None:
    """A hop written as a product of two exact literals must survive reversal.

    One foot-pound-force is a pound-force (exactly 4.4482216152605 N) through a
    foot (exactly 0.3048 m). Neither factor alone is the answer, and the single
    equivalent decimal - 1.3558179483314004 - has 17 significant digits, more
    than the engine can parse as a literal. The product form is exact in
    ``Decimal`` either way, forwards and reversed.
    """

    outcome = convert_units(
        CONVERSION_BY_NAME["Energy Conversion"],
        Decimal("1"),
        "energy_foot_pound_force",
        "energy_joule",
    )
    step, = outcome.steps
    assert step.applied_formula == "x * 4.4482216152605 * 0.3048"
    assert format_conversion_value(outcome.value) == "1.3558179483314004"

    back = convert_units(
        CONVERSION_BY_NAME["Energy Conversion"],
        Decimal("1.3558179483314004"),
        "energy_joule",
        "energy_foot_pound_force",
    )
    (reverse_step,) = back.steps
    assert reverse_step.used_backwards is True
    assert reverse_step.applied_formula == "x / 0.3048 / 4.4482216152605"
    assert format_conversion_value(back.value) == "1"



