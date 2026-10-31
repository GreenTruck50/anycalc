"""The expression engine behind both calculator pads.

:func:`calculate` parses an expression with ``ast`` and evaluates it on
``Decimal`` values. The two pads feed it two different dialects of ``%``:

* the scientific pad sends ``%`` through as Python's modulo operator, exactly as
  it was typed, and
* the regular pad's ``%`` is the percent key of a physical calculator - postfix,
  so it cannot be parsed as it stands. :func:`apply_percent_operators` rewrites
  it into a marker call (:data:`PERCENT_FUNCTION`) and the evaluator gives that
  call its meaning: a lone ``50%`` is a hundredth, and beside ``+`` or ``-`` the
  key takes that share of the number on its left, so ``200+10%`` is 220.

:func:`toggle_sign` backs the ``±`` key, which edits the number the display
rests on instead of appending an operator.

Everything here is a plain function over plain data - no Flet, no app host - so
``tests/test_calculator_engine.py`` runs it under bare pytest.
"""

import ast
import math
import operator
import re
from decimal import Decimal, DivisionByZero, InvalidOperation, Overflow

from config import (
    ERROR_DIVIDE_BY_ZERO,
    ERROR_EXPONENT_TOO_LARGE,
    ERROR_EXPRESSION_TOO_LONG,
    ERROR_INVALID_EXPRESSION,
    ERROR_INVALID_FUNCTION,
    ERROR_INVALID_NUMBER,
    ERROR_INVALID_OPERATOR,
    ERROR_INVALID_RESULT,
    ERROR_NUMBER_OVERFLOW,
    ERROR_UNKNOWN_CONSTANT,
    MAX_EXPRESSION_LENGTH,
    MAX_EXPONENT,
)
from pi import program_pi


def is_number(value) -> bool:
    """Whether a value reads as a finite number (the display holds text)."""

    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


# A numeric literal, matched whole so that a scientific-notation exponent stays
# part of its number: "1e-5" is one number, not "1e" followed by "5".
NUMBER_LITERAL = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")

# Operators that still expect a number after them, so an expression ending on one
# is half-entered. "%" is deliberately absent: on the regular pad it closes a
# number instead of opening one, and only the scientific pad uses it as modulo
# (see toggle_sign). The keys are labelled "×", "÷" and "−" but stored as ASCII;
# both spellings are listed because the display field can be typed into.
BINARY_OPERATOR_CHARACTERS = ("+", "-", "*", "/", "^", "−", "×", "÷")


# ----------------------------
# The percent key
# ----------------------------

# The regular calculator's "%" is the percent key of a physical calculator: on its
# own it divides by a hundred ("50%" is 0.5) and beside "+" or "-" it takes that
# share of the number on its left ("200+10%" is 220). A postfix "%" is not valid
# Python syntax, so the key is rewritten into a call of this marker name before
# parsing and the evaluator gives the call its meaning.
PERCENT_FUNCTION = "_percent"


def is_percent_call(node: ast.AST) -> bool:
    """Whether a node is the marker call the percent key is rewritten into."""

    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == PERCENT_FUNCTION
        and len(node.args) == 1
        and not node.keywords
    )


def _percent_operand_start(text: str, end: int) -> int:
    """Where the operand ending just before ``text[end]`` starts, or -1 if none.

    An operand is a number, a name ("pi", a variable) or a bracketed group with an
    optional function name in front of it ("sqrt(4)") - the things the "%" key can
    sensibly follow.
    """
    while end > 0 and text[end - 1].isspace():
        end -= 1
    if end == 0:
        return -1

    last = text[end - 1]

    if last == ")":
        depth = 0
        for position in range(end - 1, -1, -1):
            if text[position] == ")":
                depth += 1
            elif text[position] == "(":
                depth -= 1
                if depth == 0:
                    start = position
                    while start > 0 and (
                        text[start - 1].isalpha() or text[start - 1] == "_"
                    ):
                        start -= 1
                    return start
        return -1

    if last.isalpha() or last == "_":
        start = end - 1
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            start -= 1
        return start

    if last.isdigit() or last == ".":
        # Matched whole, so an exponent stays part of its number: "1e-5%" is one
        # operand rather than "1e-5" followed by a stray key.
        operand = None
        for candidate in NUMBER_LITERAL.finditer(text, 0, end):
            operand = candidate
        if operand is not None and operand.end() == end:
            return operand.start()

    return -1


def apply_percent_operators(expression: str) -> str:
    """Rewrite the percent key of the regular pad into marker calls.

    "200+10%" becomes "200+_percent(10)" and a lone "50%" becomes "_percent(50)".
    A "%" with nothing in front of it - the key pressed first, or straight after
    another operator - has nothing to take a percent of, so it is dropped the way
    a physical calculator ignores it.
    """
    text = expression
    index = text.find("%")
    while index != -1:
        start = _percent_operand_start(text, index)
        if start < 0:
            text = text[:index] + text[index + 1:]
            index = text.find("%", index)
            continue

        wrapped = f"{PERCENT_FUNCTION}({text[start:index]})"
        text = f"{text[:start]}{wrapped}{text[index + 1:]}"
        index = text.find("%", start + len(wrapped))
    return text


def toggle_sign(expression: str, percent_is_modulo: bool = False) -> str:
    """Flip the sign of the number the display rests on.

    "±" is a sign change, not an operator, so it never appends to the expression
    the way "+" or "-" would: it edits the number the user is working on, which is
    the last number typed (and, straight after "=", the result itself). The number
    stays where it sits, so "5 * 3" becomes "5 * -3" rather than "-5 * 3".

    Two details make the edit land where the user means it:

    * An odd number of signs in front of the number means it is already negative,
      in which case one sign is removed rather than another added. Only unary
      signs count: in a run of minuses glued to the front of a number the first one
      is a subtraction when something numeric precedes it ("5-3"), while the whole
      run is signs when an operator, an opening bracket or the start of the
      expression does ("5*-3", "-5").
    * If the expression does not end on that number but on a binary operator
      ("5-"), the user is mid-way through entering the next number, so the sign
      goes at the end instead: "5-" becomes "5--", and typing 3 gives 5 - (-3).
      A closing bracket and the regular pad's closing "%" are not binary
      operators, so "(5+3)" and "200+10%" negate their last number instead; on
      the scientific pad, where "%" is the modulo operator, "9%" is mid-entry.

    An expression with no number in it ("" or "sin(") has nothing to negate and is
    returned unchanged.
    """
    last = None
    for match in NUMBER_LITERAL.finditer(expression):
        last = match
    if last is None:
        return expression

    operators = BINARY_OPERATOR_CHARACTERS
    if percent_is_modulo:
        operators += ("%",)

    trailing = expression[last.end():].rstrip()
    signed_mid_entry = trailing.endswith(operators)
    pos = len(expression) if signed_mid_entry else last.start()

    run = 0
    while pos - run - 1 >= 0 and expression[pos - run - 1] == "-":
        run += 1

    leading = expression[: pos - run]
    subtraction = bool(leading) and (
        leading[-1].isdigit() or leading[-1].isalpha() or leading[-1] in ")."
    )
    signs = (run - 1) if (subtraction and run) else run

    if signs % 2:
        # Already negative: drop the sign touching the number.
        return expression[: pos - 1] + expression[pos:]
    return f"{expression[:pos]}-{expression[pos:]}"


def _program_pi_value(pi_provider=None) -> Decimal:
    """The pi an expression multiplies by: the program's own, or a caller's.

    :func:`pi.program_pi` holds the value the app computed for itself, so ``pi``
    on either pad means the same digits the Pi page shows rather than the
    15-decimal float ``math.pi``. ``pi_provider`` is the seam a test uses to hand
    over a known pi.
    """

    value = program_pi() if pi_provider is None else pi_provider()
    if value is None:
        # A provider that hands over nothing - no run finished yet - leaves the
        # program on its own pi rather than on nothing at all.
        value = program_pi()
    return value if isinstance(value, Decimal) else Decimal(str(value))


def calculate(expression, scientific, degrees=False, variables=None, pi_provider=None):
    binary_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
    }

    unary_ops = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def trig(function):
        def wrapped(value):
            if degrees:
                value = math.radians(value)
            return function(value)
        return wrapped

    functions = {
        "sqrt": math.sqrt,
        "sin": trig(math.sin),
        "cos": trig(math.cos),
        "tan": trig(math.tan),
        "log": math.log10,
        "ln": math.log,
        "abs": abs,
    }

    constants = {
        # "pi" is not ``math.pi``. The app computes its own pi at startup and the
        # Pi page can replace it, so every calculation in the program reads the
        # same value from ``pi.program_pi`` - see that module. A caller (a test)
        # can hand over its own pi instead.
        "pi": _program_pi_value(pi_provider),
        "π": _program_pi_value(pi_provider),   # U+03C0 GREEK SMALL LETTER PI
        "ϖ": _program_pi_value(pi_provider),   # U+03D6 GREEK PI SYMBOL
        "ℼ": _program_pi_value(pi_provider),   # U+213C DOUBLE-STRUCK SMALL PI
        "𝛑": _program_pi_value(pi_provider),   # U+1D6D1 MATHEMATICAL BOLD SMALL PI
        "𝜛": _program_pi_value(pi_provider),   # U+1D6E1 MATHEMATICAL BOLD PI SYMBOL
        "𝜋": _program_pi_value(pi_provider),   # U+1D70B MATHEMATICAL ITALIC SMALL PI
        "𝜛": _program_pi_value(pi_provider),   # U+1D71B MATHEMATICAL ITALIC PI SYMBOL
        "𝝅": _program_pi_value(pi_provider),   # U+1D745 MATHEMATICAL BOLD ITALIC SMALL PI
        "𝜛": _program_pi_value(pi_provider),   # U+1D755 MATHEMATICAL BOLD ITALIC PI SYMBOL
        "𝝿": _program_pi_value(pi_provider),   # U+1D77F MATHEMATICAL SANS-SERIF BOLD SMALL PI
        "𝝿": _program_pi_value(pi_provider),   # U+1D78F MATHEMATICAL SANS-SERIF BOLD PI SYMBOL
        "𝝅": _program_pi_value(pi_provider),   # U+1D7B9 MATHEMATICAL SANS-SERIF BOLD ITALIC SMALL PI
        "𝝅": _program_pi_value(pi_provider),   # U+1D7C9 MATHEMATICAL SANS-SERIF BOLD ITALIC PI SYMBOL
        "e": math.e,
    }
    variables = variables or {}

    def percent_share(node, total, op):
        """The percent key's share of ``total``, or None if it is not a percent.

        Only ``+`` and ``-`` take a share of the number on their left; a leading
        sign ("200+-10%") is folded into that share rather than rejected.
        """
        if op not in (ast.Add, ast.Sub):
            return None

        sign = 1
        while (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.USub, ast.UAdd))
        ):
            if isinstance(node.op, ast.USub):
                sign = -sign
            node = node.operand

        if not is_percent_call(node):
            return None
        return sign * total * evaluate(node.args[0]) / Decimal(100)

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)

        if isinstance(node, ast.Constant):
            if type(node.value) in (int, float):
                # Check for infinity/NaN from scientific notation overflow
                if isinstance(node.value, float) and not math.isfinite(node.value):
                    raise ValueError(ERROR_NUMBER_OVERFLOW)
                # Use Decimal for arbitrary precision
                return Decimal(str(node.value))
            raise ValueError(ERROR_INVALID_NUMBER)

        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in binary_ops:
                raise ValueError(ERROR_INVALID_OPERATOR)

            left = evaluate(node.left)
            # "200+10%" on a desk calculator is 200 plus ten percent *of 200*, so a
            # percent key beside an addition or a subtraction takes its share of
            # whatever is on its left. "200*10%" and "200/10%" use the plain
            # fraction instead and need no special case.
            share = percent_share(node.right, left, op)
            right = evaluate(node.right) if share is None else share

            if op is ast.Pow and abs(right) > MAX_EXPONENT:
                raise ValueError(ERROR_EXPONENT_TOO_LARGE)

            try:
                result = binary_ops[op](left, right)
            except DivisionByZero:
                raise ValueError(ERROR_DIVIDE_BY_ZERO)
            except Overflow:
                raise ValueError(ERROR_NUMBER_OVERFLOW)
            except InvalidOperation:
                raise ValueError(ERROR_INVALID_RESULT)

            if isinstance(result, complex):
                raise ValueError(ERROR_INVALID_RESULT)

            # Check for infinity/NaN
            if not result.is_finite():
                raise ValueError(ERROR_NUMBER_OVERFLOW)

            return result

        if isinstance(node, ast.UnaryOp):
            op = type(node.op)
            if op not in unary_ops:
                raise ValueError(ERROR_INVALID_OPERATOR)
            return unary_ops[op](evaluate(node.operand))

        if is_percent_call(node):
            # On its own the percent key simply divides by a hundred: "50%" is 0.5.
            return evaluate(node.args[0]) / Decimal(100)

        if isinstance(node, ast.Name) and scientific:
            if node.id in variables:
                return variables[node.id]
            if node.id in constants:
                # A constant is already a Decimal - pass it through rather than
                # round-tripping it through str, which for a pi computed to
                # millions of digits would cost more than the calculation itself.
                value = constants[node.id]
                return value if isinstance(value, Decimal) else Decimal(str(value))
            raise ValueError(ERROR_UNKNOWN_CONSTANT)

        if isinstance(node, ast.Call) and scientific:
            if not isinstance(node.func, ast.Name):
                raise ValueError(ERROR_INVALID_FUNCTION)

            name = node.func.id
            if name not in functions or len(node.args) != 1:
                raise ValueError(ERROR_INVALID_FUNCTION)

            arg = evaluate(node.args[0])
            try:
                result = functions[name](arg)
                return Decimal(str(result))
            except (ValueError, OverflowError, ZeroDivisionError):
                raise ValueError(ERROR_NUMBER_OVERFLOW)

        raise ValueError(ERROR_INVALID_EXPRESSION)

    if not expression.strip():
        return "0"

    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(ERROR_EXPRESSION_TOO_LONG)

    # The two pads print "%" differently. The scientific pad means the modulo
    # operator, which Python parses as it stands; the regular pad means the
    # percent key of a physical calculator, which is postfix and has to be
    # rewritten into something parseable first.
    program = expression if scientific else apply_percent_operators(expression)

    if not program.strip():
        # A lone percent key has nothing to take a percent of, so the display
        # stays at zero rather than reporting a broken expression.
        return "0"

    try:
        tree = ast.parse(program.replace("^", "**"), mode="eval")
    except SyntaxError:
        raise ValueError(ERROR_INVALID_EXPRESSION)
    result = evaluate(tree)

    # Format result - remove trailing zeros for cleaner display
    try:
        if result == result.to_integral_value():
            return str(result.quantize(Decimal('1')))
        else:
            # Use normalize to remove trailing zeros
            return format(result.normalize(), 'f')
    except (InvalidOperation, Overflow):
        # Fallback for very large numbers
        return format(result, 'f')

