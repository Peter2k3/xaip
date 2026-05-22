"""
xaip endpoints — listar, mostrar y generar curl de endpoints
"""
from __future__ import annotations

import fnmatch
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from xaip.commands.utils import load_config, output_json

console = Console()
app = typer.Typer(help="Gestionar endpoints escaneados")


@app.command("list")
def endpoints_list(
    controller: Optional[str] = typer.Option(None, "--controller", "-c"),
    method: Optional[str] = typer.Option(None, "--method", "-m"),
    path_glob: Optional[str] = typer.Option(None, "--path"),
    tag: Optional[str] = typer.Option(None, "--tag"),
    config: Optional[str] = typer.Option(None, "--config"),
    output_fmt: str = typer.Option("json", "--output", "-o"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    cfg, _ = load_config(config)
    eps = cfg.endpoints

    if controller:
        eps = [e for e in eps if e.controller == controller]
    if method:
        eps = [e for e in eps if e.method.value == method.upper()]
    if path_glob:
        eps = [e for e in eps if fnmatch.fnmatch(e.path, path_glob)]
    if tag:
        eps = [e for e in eps if tag in e.tags]

    data = [e.model_dump(by_alias=True, exclude_none=True) for e in eps]

    if output_fmt == "table":
        t = Table("ID", "Method", "Path", "Controller")
        for e in eps:
            t.add_row(e.id, e.method.value, e.path, e.controller or "")
        console.print(t)
    else:
        output_json(data, quiet)


@app.command("show")
def endpoints_show(
    endpoint_id: str = typer.Argument(..., help="ID del endpoint, ej: catalogo.crearCuenta"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    cfg, _ = load_config(config)
    ep = cfg.get_endpoint(endpoint_id)
    if not ep:
        console.print(f"[red]Endpoint '{endpoint_id}' no encontrado.[/red]")
        raise typer.Exit(1)

    data = ep.model_dump(by_alias=True, exclude_none=True)
    # Agregar ejemplo curl
    env = cfg.get_active_env()
    base = env.base_url if env else "http://localhost"
    data["curl"] = _build_curl(ep.method.value, f"{base}{ep.path}", {}, None)

    output_json(data, quiet)


@app.command("curl")
def endpoints_curl(
    endpoint_id: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, _ = load_config(config)
    ep = cfg.get_endpoint(endpoint_id)
    if not ep:
        console.print(f"[red]Endpoint '{endpoint_id}' no encontrado.[/red]")
        raise typer.Exit(1)

    env = cfg.get_active_env()
    base = env.base_url if env else "http://localhost"

    # Construir un body fixture si tiene schema
    body = None
    if ep.body_schema:
        body = _fixture_from_schema(ep.body_schema)

    print(_build_curl(ep.method.value, f"{base}{ep.path}", {}, body))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_curl(method: str, url: str, headers: dict, body: object | None) -> str:
    parts = [f"curl -X {method} '{url}'"]
    for k, v in headers.items():
        parts.append(f"  -H '{k}: {v}'")
    if body is not None:
        parts.append(f"  -H 'Content-Type: application/json'")
        parts.append(f"  -d '{json.dumps(body)}'")
    return " \\\n".join(parts)


def _fixture_from_schema(schema: dict) -> dict:
    result = {}
    for prop, pdef in schema.get("properties", {}).items():
        t = pdef.get("type", "string")
        if t == "string":
            result[prop] = "string"
        elif t in ("integer", "number"):
            result[prop] = 0
        elif t == "boolean":
            result[prop] = True
        elif t == "array":
            result[prop] = []
        elif t == "object":
            result[prop] = {}
    return result
