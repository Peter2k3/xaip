"""
Extracción de valores de response para --save.
Soporta JSONPath y acceso a headers.
"""
from __future__ import annotations

from typing import Any

from jsonpath_ng import parse as jp_parse


class ValueExtractor:
    """
    Extrae valores de un response dado una expresión como:
    - body.id
    - body.items[0].codigo
    - headers.Location
    - headers.Authorization
    """

    def extract(
        self,
        expr: str,
        body: Any,
        headers: dict[str, str],
        status: int,
    ) -> Any:
        expr = expr.strip()
        if expr.startswith("headers."):
            key = expr[len("headers."):]
            return headers.get(key) or headers.get(key.lower())
        if expr == "status":
            return status
        if expr.startswith("body"):
            return self._jsonpath(expr, body)
        # Intentar como JSONPath directo
        return self._jsonpath(f"body.{expr}", body)

    def _jsonpath(self, expr: str, body: Any) -> Any:
        # Normalizar: body.foo → $.foo
        if expr.startswith("body."):
            path = "$." + expr[len("body."):]
        elif expr == "body":
            return body
        elif expr.startswith("body["):
            path = "$" + expr[len("body"):]
        else:
            path = expr if expr.startswith("$") else "$." + expr

        try:
            parsed = jp_parse(path)
            matches = [m.value for m in parsed.find(body or {})]
            if not matches:
                return None
            return matches[0] if len(matches) == 1 else matches
        except Exception:
            return None
