"""
Resolución de variables de template: {{env.var}}, {{session.var}}, {{step.var}}
Pattern: Strategy + Template Method
"""
from __future__ import annotations

import re
from typing import Any

_VAR_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


class VariableResolver:
    """
    Resuelve expresiones {{...}} en strings.

    Namespaces:
    - env.KEY           → variable del entorno activo
    - session.KEY       → variable de sesión temporal
    - <stepId>.KEY      → variable guardada de un paso previo
    - KEY               → busca en todos los namespaces en orden
    """

    def __init__(
        self,
        env_vars: dict[str, Any] | None = None,
        session_vars: dict[str, Any] | None = None,
        step_vars: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._env: dict[str, Any] = env_vars or {}
        self._session: dict[str, Any] = session_vars or {}
        self._steps: dict[str, dict[str, Any]] = step_vars or {}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set_session(self, key: str, value: Any) -> None:
        self._session[key] = value

    def set_step(self, step_id: str, data: dict[str, Any]) -> None:
        """Almacena el resultado completo de un paso para {{stepId.key.nested}}."""
        self._steps[step_id] = data

    def get(self, expr: str) -> Any:
        return self._resolve_expr(expr.strip())

    def resolve(self, value: Any) -> Any:
        """Resuelve recursivamente strings, listas y dicts."""
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_string(self, text: str) -> Any:
        matches = list(_VAR_RE.finditer(text))
        if not matches:
            return text
        # Si el string ES exactamente una variable, devolver el valor nativo
        if len(matches) == 1 and matches[0].group(0) == text:
            val = self._resolve_expr(matches[0].group(1).strip())
            return val if val is not None else text
        # Caso general: interpolación de strings
        def replacer(m: re.Match) -> str:
            val = self._resolve_expr(m.group(1).strip())
            return str(val) if val is not None else m.group(0)
        return _VAR_RE.sub(replacer, text)

    def _resolve_expr(self, expr: str) -> Any:
        if "." in expr:
            namespace, _, key = expr.partition(".")
            if namespace == "env":
                return self._env.get(key)
            if namespace == "session":
                return self._session.get(key)
            if namespace in self._steps:
                return self._get_nested(self._steps[namespace], key)
        # Sin namespace: buscar en orden
        for store in (self._session, self._env):
            if expr in store:
                return store[expr]
        return None

    @staticmethod
    def _get_nested(obj: Any, path: str) -> Any:
        """Acceso a rutas anidadas separadas por punto."""
        for part in path.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
        return obj

    def snapshot(self) -> dict[str, Any]:
        """Devuelve el estado actual para debug."""
        return {
            "env": dict(self._env),
            "session": dict(self._session),
            "steps": {k: dict(v) for k, v in self._steps.items()},
        }
