"""The unit conversion engine: configuration, routes, formulas.

``src/assets/conversions.yaml`` declares the unit groups and, for every
conversion menu entry, the formulas that connect pairs of units. A route between
two units is found breadth-first over those formulas: forward edges only first,
and only when no forward route exists are "MD" (multiply/divide) edges walked
backwards - which also covers offset formulas such as Celsius to Fahrenheit, by
solving the formula for ``x`` (:func:`_invert_conversion_formula`) rather than
by storing a second copy of it.

Every function here is plain data in, plain data out - no page, no widgets - so
``tests/test_conversion_engine.py`` runs it under bare pytest.
"""

import ast
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import flet as ft
import yaml

from calculate import calculate
from config import CONVERSION_CONFIG_PATH


def load_conversion_config() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = yaml.safe_load(CONVERSION_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Conversion configuration must be a YAML mapping")

    unit_groups = config.get("units")
    conversions = config.get("conversions")
    if not isinstance(unit_groups, list) or not isinstance(conversions, list):
        raise ValueError("Conversion configuration must define units and conversions")

    unit_ids: set[str] = set()
    for group in unit_groups:
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("name"), str)
            or not isinstance(group.get("units"), list)
        ):
            raise ValueError("Each conversion unit group must contain a units list")
        for unit in group["units"]:
            if (
                not isinstance(unit, dict)
                or not isinstance(unit.get("id"), str)
                or not isinstance(unit.get("name"), str)
                or not isinstance(unit.get("symbol"), str)
            ):
                raise ValueError("Each conversion unit must define a name, symbol, and id")
            if unit["id"] in unit_ids:
                raise ValueError(f"Duplicate conversion unit id: {unit['id']}")
            guidance = unit.get("guidance")
            if guidance is not None and (
                not isinstance(guidance, str) or not guidance.strip()
            ):
                raise ValueError(
                    f"Guidance for conversion unit {unit['id']} must be text"
                )
            unit_ids.add(unit["id"])

    for conversion in conversions:
        if (
            not isinstance(conversion, dict)
            or not isinstance(conversion.get("formulas"), dict)
            or not conversion["formulas"]
        ):
            raise ValueError("Each conversion menu item must define formulas")
        if not isinstance(conversion.get("name"), str):
            raise ValueError("Each conversion menu item must define a name")
        if (
            not isinstance(conversion.get("description"), str)
            or not isinstance(conversion.get("icon"), str)
            or not conversion["icon"].startswith("ft.Icons.")
        ):
            raise ValueError(
                "Each conversion menu item must define a description and Flet icon"
            )
        icon_name = conversion["icon"].rsplit(".", 1)[-1]
        if not hasattr(ft.Icons, icon_name):
            raise ValueError(f"Unknown Flet icon: {conversion['icon']}")
        for formula in conversion["formulas"].values():
            if not isinstance(formula, dict):
                raise ValueError("Each conversion formula must be a mapping")
            if formula.get("type") not in ("MD", "UD"):
                raise ValueError("Conversion formula type must be MD or UD")
            if formula.get("input_unit_id") not in unit_ids:
                raise ValueError(
                    f"Unknown input unit id: {formula.get('input_unit_id')}"
                )
            if formula.get("output_unit_id") not in unit_ids:
                raise ValueError(
                    f"Unknown output unit id: {formula.get('output_unit_id')}"
                )
            formula_text = formula.get("formula")
            if not isinstance(formula_text, str):
                raise ValueError("Each conversion formula must define a formula string")
            parsed_formula = ast.parse(formula_text, mode="eval")
            if not _contains_conversion_input(parsed_formula):
                raise ValueError("Each conversion formula must use lowercase x")
            if formula["type"] == "MD":
                forward_value = _evaluate_conversion_formula(
                    formula_text, Decimal("1")
                )
                _invert_conversion_formula(formula_text, forward_value)

    return unit_groups, conversions


def find_conversion_path(
    conversion: dict[str, Any],
    source_unit_id: str,
    target_unit_id: str,
) -> list[tuple[dict[str, Any], bool]] | None:
    if source_unit_id == target_unit_id:
        return []

    formulas = list(conversion["formulas"].values())

    def search(allow_reverse: bool) -> list[tuple[dict[str, Any], bool]] | None:
        queue = deque([(source_unit_id, [])])
        visited = {source_unit_id}

        while queue:
            current_unit_id, path = queue.popleft()
            for formula in formulas:
                edges = [
                    (formula["input_unit_id"], formula["output_unit_id"], False)
                ]
                if allow_reverse and formula["type"] == "MD":
                    edges.append(
                        (formula["output_unit_id"], formula["input_unit_id"], True)
                    )

                for edge_source, edge_target, reverse in edges:
                    if edge_source != current_unit_id or edge_target in visited:
                        continue
                    next_path = [*path, (formula, reverse)]
                    if edge_target == target_unit_id:
                        return next_path
                    visited.add(edge_target)
                    queue.append((edge_target, next_path))

        return None

    forward_path = search(allow_reverse=False)
    if forward_path is not None:
        return forward_path
    return search(allow_reverse=True)


def _contains_conversion_input(node: ast.AST) -> bool:
    return any(
        isinstance(part, ast.Name) and part.id == "x"
        for part in ast.walk(node)
    )


def _evaluate_conversion_formula(formula: str, value: Decimal) -> Decimal:
    result = calculate(formula, scientific=True, variables={"x": value})
    return Decimal(result)


def _invert_conversion_formula(formula: str, target: Decimal) -> Decimal:
    tree = ast.parse(formula, mode="eval")

    def solve(node: ast.AST, value: Decimal) -> Decimal:
        if isinstance(node, ast.Expression):
            return solve(node.body, value)
        if isinstance(node, ast.Name) and node.id == "x":
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            return solve(
                node.operand,
                -value if isinstance(node.op, ast.USub) else value,
            )
        if not isinstance(node, ast.BinOp):
            raise ValueError("This MD formula cannot be reversed")

        left_has_input = _contains_conversion_input(node.left)
        right_has_input = _contains_conversion_input(node.right)
        if left_has_input == right_has_input:
            raise ValueError("This MD formula cannot be reversed")

        constant_node = node.right if left_has_input else node.left
        constant = Decimal(calculate(ast.unparse(constant_node), scientific=False))

        if isinstance(node.op, ast.Add):
            inverse_value = value - constant
        elif isinstance(node.op, ast.Sub):
            inverse_value = (
                value + constant if left_has_input else constant - value
            )
        elif isinstance(node.op, ast.Mult):
            inverse_value = value / constant
        elif isinstance(node.op, ast.Div):
            inverse_value = (
                value * constant if left_has_input else constant / value
            )
        else:
            raise ValueError("This MD formula cannot be reversed")

        return solve(
            node.left if left_has_input else node.right,
            inverse_value,
        )

    return solve(tree, target)


def _flip_conversion_formula(formula: str) -> str:
    """Reverse an MD formula for display, e.g. "x / 100" becomes "x * 100".

    Mirrors the algebra of _invert_conversion_formula, but instead of applying
    the reversal it builds the reversed formula, so the chain view can show the
    formula exactly as it was used.
    """
    tree = ast.parse(formula, mode="eval")

    def reversed_dividend(value: ast.expr, constant: ast.expr) -> ast.BinOp:
        # Dividing by a fraction reads better as multiplying by its reciprocal:
        # "x / (5 / 9)" becomes "x * (9 / 5)".
        if isinstance(constant, ast.BinOp) and isinstance(constant.op, ast.Div):
            reciprocal = ast.BinOp(
                op=ast.Div(),
                left=constant.right,
                right=constant.left,
            )
            return ast.BinOp(op=ast.Mult(), left=value, right=reciprocal)
        return ast.BinOp(op=ast.Div(), left=value, right=constant)

    def flip(node: ast.AST, value: ast.expr) -> ast.expr:
        if isinstance(node, ast.Expression):
            return flip(node.body, value)
        if isinstance(node, ast.Name) and node.id == "x":
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            negated = (
                value
                if isinstance(node.op, ast.UAdd)
                else ast.UnaryOp(op=ast.USub(), operand=value)
            )
            return flip(node.operand, negated)
        if not isinstance(node, ast.BinOp):
            raise ValueError("This MD formula cannot be reversed")

        left_has_input = _contains_conversion_input(node.left)
        right_has_input = _contains_conversion_input(node.right)
        if left_has_input == right_has_input:
            raise ValueError("This MD formula cannot be reversed")

        constant = node.right if left_has_input else node.left
        if isinstance(node.op, ast.Add):
            reversed_value = ast.BinOp(op=ast.Sub(), left=value, right=constant)
        elif isinstance(node.op, ast.Sub):
            reversed_value = (
                ast.BinOp(op=ast.Add(), left=value, right=constant)
                if left_has_input
                else ast.BinOp(op=ast.Sub(), left=constant, right=value)
            )
        elif isinstance(node.op, ast.Mult):
            reversed_value = reversed_dividend(value, constant)
        elif isinstance(node.op, ast.Div):
            reversed_value = (
                ast.BinOp(op=ast.Mult(), left=value, right=constant)
                if left_has_input
                else ast.BinOp(op=ast.Div(), left=constant, right=value)
            )
        else:
            raise ValueError("This MD formula cannot be reversed")

        return flip(node.left if left_has_input else node.right, reversed_value)

    placeholder = ast.Name(id="x", ctx=ast.Load())
    return ast.unparse(flip(tree, placeholder))


@dataclass(frozen=True)
class ConversionStep:
    """One hop of a conversion chain, exactly as it was applied."""

    from_unit_id: str
    to_unit_id: str
    formula: str
    applied_formula: str
    formula_type: str
    used_backwards: bool
    input_value: Decimal
    output_value: Decimal


@dataclass(frozen=True)
class ConversionOutcome:
    value: Decimal
    steps: list[ConversionStep]


def format_conversion_value(value: Decimal) -> str:
    return format(value.normalize(), "f")


def convert_units(
    conversion: dict[str, Any],
    value: Decimal,
    source_unit_id: str,
    target_unit_id: str,
) -> ConversionOutcome:
    path = find_conversion_path(conversion, source_unit_id, target_unit_id)
    if path is None:
        raise ValueError("No conversion path is defined for those units")

    result = value
    steps: list[ConversionStep] = []
    for formula, reverse in path:
        step_input = result
        if reverse:
            result = _invert_conversion_formula(formula["formula"], result)
            from_unit_id = formula["output_unit_id"]
            to_unit_id = formula["input_unit_id"]
            try:
                applied_formula = _flip_conversion_formula(formula["formula"])
            except ValueError:
                applied_formula = formula["formula"]
        else:
            result = _evaluate_conversion_formula(formula["formula"], result)
            from_unit_id = formula["input_unit_id"]
            to_unit_id = formula["output_unit_id"]
            applied_formula = formula["formula"]
        steps.append(
            ConversionStep(
                from_unit_id=from_unit_id,
                to_unit_id=to_unit_id,
                formula=formula["formula"],
                applied_formula=applied_formula,
                formula_type=formula["type"],
                used_backwards=reverse,
                input_value=step_input,
                output_value=result,
            )
        )
    return ConversionOutcome(value=result, steps=steps)
