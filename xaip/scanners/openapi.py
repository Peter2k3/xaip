"""
Scanner para OpenAPI spec (JSON o YAML, desde archivo o URL).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xaip.core.models import EndpointSchema, HttpMethod, ParamSchema
from xaip.scanners.base import BaseScanner

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class OpenApiScanner(BaseScanner):
    """Lee una spec OpenAPI 3.x y convierte a EndpointSchema."""

    @property
    def name(self) -> str:
        return "openapi"

    def can_handle(self, root: Path) -> bool:
        return False  # Solo se usa explícitamente, no por auto-detección

    def scan(self, root: Path) -> list[EndpointSchema]:
        return []

    def scan_spec(self, spec: dict[str, Any]) -> list[EndpointSchema]:
        endpoints: list[EndpointSchema] = []
        paths = spec.get("paths", {})
        for route_path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method.lower() not in _HTTP_METHODS:
                    continue
                if not isinstance(operation, dict):
                    continue
                try:
                    http_method = HttpMethod(method.upper())
                except ValueError:
                    continue

                tags = operation.get("tags", [])
                op_id = operation.get("operationId", "")
                description = operation.get("summary") or operation.get("description") or ""

                params: list[ParamSchema] = []
                for p in operation.get("parameters", []):
                    params.append(ParamSchema(
                        name=p.get("name", ""),
                        location=p.get("in", "query"),
                        required=p.get("required", False),
                        description=p.get("description"),
                    ))

                body_schema: dict | None = None
                req_body = operation.get("requestBody", {})
                if req_body:
                    content = req_body.get("content", {})
                    json_content = content.get("application/json", {})
                    body_schema = json_content.get("schema")

                # Generar ID
                if op_id:
                    ep_id = op_id
                else:
                    parts = [p for p in route_path.split("/") if p and not p.startswith("{")]
                    ep_id = f"{''.join(p.capitalize() for p in parts) or 'root'}.{method.lower()}"

                endpoints.append(EndpointSchema(
                    id=ep_id,
                    method=http_method,
                    path=route_path,
                    tags=tags,
                    params=params,
                    body_schema=body_schema,
                    description=description,
                ))
        return endpoints

    def load_from_file(self, path: Path) -> list[EndpointSchema]:
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                spec = yaml.safe_load(text)
            except ImportError:
                raise RuntimeError("PyYAML no instalado. Instala con: pip install pyyaml")
        else:
            spec = json.loads(text)
        return self.scan_spec(spec)

    async def load_from_url(self, url: str) -> list[EndpointSchema]:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=30)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "yaml" in ct:
                try:
                    import yaml
                    spec = yaml.safe_load(resp.text)
                except ImportError:
                    raise RuntimeError("PyYAML no instalado.")
            else:
                spec = resp.json()
        return self.scan_spec(spec)
