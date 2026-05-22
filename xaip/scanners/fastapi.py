"""
Scanner para FastAPI — parsea decoradores @app.get, @router.post, etc.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from xaip.core.models import EndpointSchema, HttpMethod, ParamSchema
from xaip.scanners.base import BaseScanner

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class FastApiScanner(BaseScanner):
    @property
    def name(self) -> str:
        return "fastapi"

    def can_handle(self, root: Path) -> bool:
        req = root / "requirements.txt"
        if req.exists() and "fastapi" in req.read_text(errors="ignore").lower():
            return True
        pyproject = root / "pyproject.toml"
        if pyproject.exists() and "fastapi" in pyproject.read_text(errors="ignore").lower():
            return True
        return False

    def scan(self, root: Path) -> list[EndpointSchema]:
        endpoints: list[EndpointSchema] = []
        for f in root.rglob("*.py"):
            if any(p in f.parts for p in ("venv", ".venv", "__pycache__", "node_modules")):
                continue
            endpoints.extend(self._scan_file(f))
        return endpoints

    def _scan_file(self, path: Path) -> list[EndpointSchema]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return []

        endpoints: list[EndpointSchema] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                ep = self._parse_decorator(decorator, path.stem)
                if ep:
                    endpoints.append(ep)
        return endpoints

    def _parse_decorator(self, decorator: ast.expr, module: str) -> EndpointSchema | None:
        # @router.get("/path") or @app.post("/path")
        if not isinstance(decorator, ast.Call):
            return None
        func = decorator.func
        if not isinstance(func, ast.Attribute):
            return None
        method_name = func.attr.lower()
        if method_name not in _HTTP_METHODS:
            return None

        # Primer argumento posicional = path
        if not decorator.args:
            return None
        first_arg = decorator.args[0]
        if not isinstance(first_arg, ast.Constant):
            return None
        route_path = str(first_arg.value)

        try:
            http_method = HttpMethod(method_name.upper())
        except ValueError:
            return None

        path_vars = re.findall(r'\{(\w+)\}', route_path)
        params = [ParamSchema(name=v, location="path", required=True) for v in path_vars]

        ep_id = f"{module}.{method_name}{self._path_to_id(route_path)}"
        return EndpointSchema(
            id=ep_id,
            controller=module,
            method=http_method,
            path=route_path,
            params=params,
        )

    @staticmethod
    def _path_to_id(path: str) -> str:
        parts = [p for p in path.split("/") if p and not p.startswith("{")]
        return "".join(p.capitalize() for p in parts) if parts else "Root"
