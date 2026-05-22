"""
Scanner para Spring Boot usando javalang para parseo de AST real.
Fallback a regex si javalang no puede parsear el archivo.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from xaip.core.models import EndpointSchema, HttpMethod, ParamSchema
from xaip.scanners.base import BaseScanner

_MAPPING_TO_METHOD = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "PatchMapping": "PATCH",
    "DeleteMapping": "DELETE",
}

_PATH_VAR_RE = re.compile(r'\{(\w+)\}')


class SpringBootScanner(BaseScanner):
    @property
    def name(self) -> str:
        return "spring-boot"

    def can_handle(self, root: Path) -> bool:
        pom = root / "pom.xml"
        if pom.exists() and "spring-boot" in pom.read_text(errors="ignore"):
            return True
        for g in ["build.gradle", "build.gradle.kts"]:
            f = root / g
            if f.exists() and "spring" in f.read_text(errors="ignore").lower():
                return True
        return False

    def scan(self, root: Path) -> list[EndpointSchema]:
        endpoints: list[EndpointSchema] = []
        for f in root.rglob("*.java"):
            if any(p in str(f) for p in ("test/", "Test.java")):
                continue
            endpoints.extend(self._scan_file(f))
        return endpoints

    def _scan_file(self, path: Path) -> list[EndpointSchema]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        try:
            return self._scan_with_javalang(source, path.stem)
        except Exception:
            pass
        return self._scan_with_regex(source, path.stem)

    # ------------------------------------------------------------------
    # javalang AST parser
    # ------------------------------------------------------------------

    def _scan_with_javalang(self, source: str, filename: str) -> list[EndpointSchema]:
        import javalang

        tree = javalang.parse.parse(source)
        endpoints: list[EndpointSchema] = []

        for _, cls in tree.filter(javalang.tree.ClassDeclaration):
            if not self._is_controller(cls):
                continue
            controller_name = cls.name
            base_path = self._extract_base_path_jl(cls)
            for method in cls.methods:
                ep = self._extract_endpoint_jl(method, base_path, controller_name)
                if ep:
                    endpoints.append(ep)
        return endpoints

    def _is_controller(self, cls: Any) -> bool:
        if not cls.annotations:
            return False
        return any(a.name in {"Controller", "RestController"} for a in cls.annotations)

    def _extract_base_path_jl(self, cls: Any) -> str:
        if not cls.annotations:
            return ""
        for anno in cls.annotations:
            if anno.name in ("RequestMapping", "Mapping"):
                path = self._anno_value(anno)
                return path.rstrip("/") if path else ""
        return ""

    def _extract_endpoint_jl(self, method: Any, base_path: str, controller_name: str) -> EndpointSchema | None:
        if not method.annotations:
            return None
        http_method_str: str | None = None
        method_path = ""
        for anno in method.annotations:
            if anno.name in _MAPPING_TO_METHOD:
                http_method_str = _MAPPING_TO_METHOD[anno.name]
                method_path = self._anno_value(anno) or ""
                break
            if anno.name == "RequestMapping":
                http_method_str = self._request_mapping_method(anno) or "GET"
                method_path = self._anno_value(anno) or ""
                break
        if not http_method_str:
            return None
        try:
            http_method = HttpMethod(http_method_str)
        except ValueError:
            return None
        full_path = self._join_paths(base_path, method_path)
        path_vars = _PATH_VAR_RE.findall(full_path)
        params = [ParamSchema(name=v, location="path", required=True) for v in path_vars]
        if method.parameters:
            for p in method.parameters:
                if p.annotations:
                    for a in p.annotations:
                        if a.name == "RequestParam":
                            params.append(ParamSchema(name=p.name, location="query", required=False))
                        elif a.name == "RequestHeader":
                            params.append(ParamSchema(name=p.name, location="header", required=False))
        ep_id = f"{self._to_camel(controller_name)}.{http_method_str.lower()}{self._path_to_id(full_path)}"
        return EndpointSchema(id=ep_id, controller=controller_name, method=http_method, path=full_path, params=params)

    def _anno_value(self, anno: Any) -> str:
        if not anno.element:
            return ""
        import javalang
        element = anno.element
        if isinstance(element, javalang.tree.Literal):
            return element.value.strip('"\'')
        if isinstance(element, list):
            for elem in element:
                if hasattr(elem, "value") and isinstance(elem.value, javalang.tree.Literal):
                    return elem.value.value.strip('"\'')
                if hasattr(elem, "value") and isinstance(elem.value, str):
                    return elem.value.strip('"\'')
        return ""

    def _request_mapping_method(self, anno: Any) -> str | None:
        if not anno.element:
            return None
        if isinstance(anno.element, list):
            for kv in anno.element:
                if hasattr(kv, "name") and kv.name == "method":
                    val = str(kv.value)
                    for m in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                        if m in val:
                            return m
        return None

    # ------------------------------------------------------------------
    # Fallback: regex scanner
    # ------------------------------------------------------------------

    def _scan_with_regex(self, source: str, filename: str) -> list[EndpointSchema]:
        if not re.search(r'@(?:Rest)?Controller\b', source):
            return []
        class_match = re.search(r'\bclass\s+(\w+)', source)
        controller_name = class_match.group(1) if class_match else filename
        base_path = ""
        cm = re.search(r'@(?:Request)?Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', source)
        if cm:
            base_path = cm.group(1).rstrip("/")
        endpoints: list[EndpointSchema] = []
        anno_re = re.compile(
            r'@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\s*(?:\(([^)]*)\))?'
        )
        path_re = re.compile(r'(?:value\s*=\s*)?["\']([^"\']+)["\']')
        for m in anno_re.finditer(source):
            anno_name = m.group(1)
            anno_body = m.group(2) or ""
            http_method_str = _MAPPING_TO_METHOD.get(anno_name, "GET")
            try:
                http_method = HttpMethod(http_method_str)
            except ValueError:
                continue
            path_m = path_re.search(anno_body)
            method_path = path_m.group(1) if path_m else ""
            full_path = self._join_paths(base_path, method_path)
            path_vars = _PATH_VAR_RE.findall(full_path)
            params = [ParamSchema(name=v, location="path", required=True) for v in path_vars]
            ep_id = f"{self._to_camel(controller_name)}.{http_method_str.lower()}{self._path_to_id(full_path)}"
            endpoints.append(EndpointSchema(id=ep_id, controller=controller_name, method=http_method, path=full_path, params=params))
        return endpoints

    # ------------------------------------------------------------------
    @staticmethod
    def _join_paths(base: str, sub: str) -> str:
        path = f"{base}/{sub.lstrip('/')}".rstrip("/") or "/"
        return re.sub(r'//+', '/', path)

    @staticmethod
    def _to_camel(name: str) -> str:
        if name.endswith("Controller"):
            name = name[: -len("Controller")]
        return name[0].lower() + name[1:] if name else name

    @staticmethod
    def _path_to_id(path: str) -> str:
        parts = [p for p in path.split("/") if p and not p.startswith("{")]
        return "".join(p.capitalize() for p in parts) if parts else "Root"
