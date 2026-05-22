"""
Motor de aserciones.
Soporta: status, body (JSONPath), headers, ms, schema.
Pattern: Chain of Responsibility
"""
from __future__ import annotations

import re
from typing import Any

from jsonpath_ng import parse as jp_parse

from xaip.core.models import AssertionResult


# Operadores soportados
_OP_RE = re.compile(
    r"^([a-zA-Z_.:\[\]0-9*@-]+?)\s*(~=|!=|>=|<=|=>|=<|>|<|=|exists)\s*(.*)$"
)


class AssertionEngine:
    """Evalúa aserciones sobre un response."""

    def evaluate(
        self,
        expr: str,
        status: int,
        headers: dict[str, str],
        body: Any,
        duration_ms: int,
    ) -> AssertionResult:
        try:
            return self._eval(expr.strip(), status, headers, body, duration_ms)
        except Exception as exc:  # noqa: BLE001
            return AssertionResult(expr=expr, passed=False, message=str(exc))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _eval(
        self,
        expr: str,
        status: int,
        headers: dict[str, str],
        body: Any,
        duration_ms: int,
    ) -> AssertionResult:
        m = _OP_RE.match(expr)
        if not m:
            return AssertionResult(expr=expr, passed=False, message="Expresión inválida")

        field, op, expected_raw = m.group(1), m.group(2), m.group(3).strip()

        # Extraer valor actual
        actual = self._extract(field, status, headers, body, duration_ms)

        if op == "exists":
            passed = actual is not None
            return AssertionResult(expr=expr, passed=passed, actual=actual)

        expected = _coerce(expected_raw)
        passed = _compare(actual, op, expected)
        return AssertionResult(
            expr=expr,
            passed=passed,
            actual=actual,
            message=None if passed else f"esperado {op} {expected}, obtenido {actual!r}",
        )

    def _extract(
        self,
        field: str,
        status: int,
        headers: dict[str, str],
        body: Any,
        duration_ms: int,
    ) -> Any:
        if field == "status":
            return status
        if field == "ms":
            return duration_ms
        if field.startswith("headers."):
            key = field[len("headers."):]
            return headers.get(key) or headers.get(key.lower())
        if field.startswith("body"):
            if field == "body":
                return body
            # JSONPath-style using jsonpath_ng
            path = field.replace("body.", "$.", 1).replace("body[", "$[", 1)
            if not path.startswith("$"):
                path = "$." + field[5:]
            try:
                expr = jp_parse(path)
                matches = [m.value for m in expr.find(body or {})]
                if not matches:
                    return None
                return matches[0] if len(matches) == 1 else matches
            except Exception:
                return None
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce(raw: str) -> Any:
    """Convierte el string esperado al tipo Python más apropiado."""
    if raw.lower() == "null":
        return None
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    # String delimitado por comillas
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    # Número
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _compare(actual: Any, op: str, expected: Any) -> bool:
    try:
        if op in ("=", "=>", "<="):  # => y <= como alias para compat
            if op == "=":
                # ~= para "contiene"
                return actual == expected
            if op == "=>":
                return actual >= expected
            if op == "<=":
                return actual <= expected
        if op == "!=":
            return actual != expected
        if op == ">=":
            return actual >= expected
        if op == "<=":
            return actual <= expected
        if op == ">":
            return actual > expected
        if op == "<":
            return actual < expected
        if op == "~=":
            return expected in str(actual)
    except TypeError:
        return False
    return False
