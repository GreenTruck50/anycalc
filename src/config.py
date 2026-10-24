"""Project configuration: numeric limits, display sizes, key names, error text.

Constants plus one path. The Decimal precision set at the bottom is process
wide, so every module that does Decimal arithmetic reaches this module first -
both engines import it, and the UI imports the engines. Nothing here imports
Flet, which is what lets the engines be imported (and tested) without an app.
"""

from decimal import getcontext
from pathlib import Path

# Display precision for Decimal calculations
DECIMAL_PRECISION = 50

# Maximum absolute exponent value for power operations
MAX_EXPONENT = 1000

# Maximum expression length
MAX_EXPRESSION_LENGTH = 200

# Maximum history items to keep
MAX_HISTORY_ITEMS = 20

# The main display line, and the small live answer shown under it while an
# expression is being typed. The live answer is promoted to display size when
# "=" is pressed, so both sizes are defined together.
DISPLAY_TEXT_SIZE = 34
DISPLAY_TEXT_COLOR = "#FFFFFF"
PREVIEW_TEXT_SIZE = 15
PREVIEW_TEXT_COLOR = "#9CA3AF"

# How long the live answer takes to grow into the display, and how far up it
# slides while doing so.
PREVIEW_MORPH_MS = 260
PREVIEW_MORPH_LIFT = 34

_NAMED_VARIABLE_OPTIONS = (
    ("x", "x"),
    ("y", "y"),
    ("z", "z"),
    ("μ", "friction / coefficient of friction"),
    ("g", "gravity"),
    ("m", "mass"),
    ("a", "acceleration"),
    ("v", "velocity"),
    ("t", "time"),
    ("d", "distance"),
    ("F", "force"),
    ("E", "energy"),
    ("P", "power"),
    ("p", "pressure"),
    ("ρ", "density"),
    ("r", "radius"),
    ("A", "area"),
    ("V", "volume"),
    ("T", "temperature"),
    ("q", "charge"),
    ("I", "current"),
    ("U", "voltage"),
    ("R", "resistance"),
    ("f", "frequency"),
    ("λ", "wavelength"),
)
_NAMED_VARIABLE_SYMBOLS = {
    option[0] for option in _NAMED_VARIABLE_OPTIONS
}
VARIABLE_OPTIONS = _NAMED_VARIABLE_OPTIONS + tuple(
    (letter, letter)
    for letter in "abcdefghijklmnopqrstuvwxyz"
    if letter not in _NAMED_VARIABLE_SYMBOLS
)
VARIABLE_NAMES = tuple(option[0] for option in VARIABLE_OPTIONS)

# Error messages
ERROR_DIVIDE_BY_ZERO = "Can't divide by 0"
ERROR_NUMBER_OVERFLOW = "Number Overflow"
ERROR_INVALID_RESULT = "Invalid result"
ERROR_EXPONENT_TOO_LARGE = "Exponent too large"
ERROR_EXPRESSION_TOO_LONG = "Expression too long"
ERROR_UNKNOWN_CONSTANT = "Unknown constant"
ERROR_INVALID_FUNCTION = "Invalid function"
ERROR_INVALID_OPERATOR = "Invalid operator"
ERROR_INVALID_NUMBER = "Invalid number"
ERROR_INVALID_EXPRESSION = "Invalid expression"


# All error messages for easy checking
ERROR_MESSAGES = (
    ERROR_DIVIDE_BY_ZERO,
    ERROR_NUMBER_OVERFLOW,
    ERROR_INVALID_RESULT,
    ERROR_EXPONENT_TOO_LARGE,
    ERROR_EXPRESSION_TOO_LONG,
    ERROR_UNKNOWN_CONSTANT,
    ERROR_INVALID_FUNCTION,
    ERROR_INVALID_OPERATOR,
    ERROR_INVALID_NUMBER,
    ERROR_INVALID_EXPRESSION,
    "Error"
)

# Use high precision for big numbers
getcontext().prec = DECIMAL_PRECISION

# The unit data ships next to the modules that read it, which is also the path
# the packaging config keeps in the artifact ([tool.setuptools.package-data]).
CONVERSION_CONFIG_PATH = Path(__file__).resolve().parent / "assets" / "conversions.yaml"
