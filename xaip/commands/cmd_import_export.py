"""
xaip import / xaip export
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from xaip.commands.utils import load_config, output_json

console = Console()

import_app = typer.Typer(help="Importar colecciones desde otras herramientas")
export_app = typer.Typer(help="Exportar colecciones")


# ---------------------------------------------------------------------------
# IMPORT
# ---------------------------------------------------------------------------

@import_app.command("openapi")
def import_openapi(
    source: str = typer.Argument(..., help="Ruta o URL al archivo OpenAPI"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, repo = load_config(config)
    from xaip.scanners.openapi import OpenApiScanner
    scanner = OpenApiScanner()

    if source.startswith("http://") or source.startswith("https://"):
        endpoints = asyncio.run(scanner.load_from_url(source))
    else:
        endpoints = scanner.load_from_file(Path(source))

    # Añadir o reemplazar endpoints
    existing_ids = {e.id for e in cfg.endpoints}
    new_eps = [e for e in endpoints if e.id not in existing_ids]
    cfg.endpoints.extend(new_eps)
    repo.save(cfg)

    console.print(f"[green]Importados {len(new_eps)} endpoints nuevos ({len(endpoints)} totales en spec).[/green]")
    output_json({"imported": len(new_eps), "total": len(endpoints)}, quiet)


@import_app.command("postman")
def import_postman(
    path: str = typer.Argument(..., help="Ruta al archivo .postman_collection.json"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, repo = load_config(config)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    from xaip.utils.importers import import_postman_collection
    collection = import_postman_collection(data)
    if cfg.get_collection(collection.id):
        console.print(f"[yellow]Colección '{collection.id}' ya existe, sobreescribiendo.[/yellow]")
        cfg.collections = [c for c in cfg.collections if c.id != collection.id]
    cfg.collections.append(collection)
    repo.save(cfg)
    console.print(f"[green]Colección '{collection.id}' importada con {len(collection.steps)} pasos.[/green]")
    output_json({"collection": collection.id, "steps": len(collection.steps)}, quiet)


@import_app.command("curl")
def import_curl(
    curl_str: str = typer.Argument(..., help="Comando curl entre comillas"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    from xaip.utils.importers import parse_curl_command
    step = parse_curl_command(curl_str)
    console.print(f"[green]Parseado: {step.request.method.value} {step.request.path}[/green]")
    output_json(step.model_dump(by_alias=True, exclude_none=True), quiet)


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

@export_app.command("pytest")
def export_pytest(
    collection_name: str = typer.Option(..., "--collection", "-c"),
    output_path: Optional[str] = typer.Option(None, "--output", "-o"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, _ = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        console.print(f"[red]Colección '{collection_name}' no encontrada.[/red]")
        raise typer.Exit(1)

    env = cfg.get_active_env()
    base_url = env.base_url if env else "http://localhost"

    code = _generate_pytest(col, base_url)
    if output_path:
        Path(output_path).write_text(code, encoding="utf-8")
        console.print(f"[green]Exportado a {output_path}[/green]")
    else:
        print(code)


@export_app.command("curl")
def export_curl(
    collection_name: str = typer.Option(..., "--collection", "-c"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, _ = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        raise typer.Exit(1)

    env = cfg.get_active_env()
    base_url = env.base_url if env else "http://localhost"

    for step in col.steps:
        req = step.request
        url = f"{base_url.rstrip('/')}/{req.path.lstrip('/')}"
        parts = [f"# {step.name or step.id}", f"curl -X {req.method.value} '{url}'"]
        for k, v in req.headers.items():
            parts.append(f"  -H '{k}: {v}'")
        if req.body:
            parts.append(f"  -H 'Content-Type: application/json'")
            parts.append(f"  -d '{json.dumps(req.body)}'")
        print(" \\\n".join(parts))
        print()


@export_app.command("markdown")
def export_markdown(
    collection_name: str = typer.Option(..., "--collection", "-c"),
    output_path: Optional[str] = typer.Option(None, "--output", "-o"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, _ = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        raise typer.Exit(1)

    lines = [f"# {col.name}\n"]
    for step in col.steps:
        req = step.request
        lines.append(f"## {step.name or step.id}\n")
        lines.append(f"**{req.method.value}** `{req.path}`\n")
        if step.depends_on:
            lines.append(f"Depende de: {', '.join(step.depends_on)}\n")
        if req.body:
            lines.append(f"```json\n{json.dumps(req.body, indent=2)}\n```\n")
        if step.expect:
            lines.append("**Aserciones:**\n")
            for e in step.expect:
                lines.append(f"- `{e}`\n")
        lines.append("")

    md = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(md, encoding="utf-8")
        console.print(f"[green]Exportado a {output_path}[/green]")
    else:
        print(md)


# ---------------------------------------------------------------------------
# Generador de pytest
# ---------------------------------------------------------------------------

def _generate_pytest(col, base_url: str) -> str:
    lines = [
        "\"\"\"",
        f"Tests generados por XAIP para colección: {col.id}",
        "\"\"\"",
        "import pytest",
        "import httpx",
        "",
        f'BASE_URL = "{base_url}"',
        "",
    ]

    # Variables compartidas entre tests (session fixture)
    lines += [
        "@pytest.fixture(scope='module')",
        "def session_vars():",
        "    return {}",
        "",
    ]

    for step in col.steps:
        req = step.request
        func_name = f"test_{step.id.replace('-', '_')}"
        lines.append(f"def {func_name}(session_vars):")
        lines.append(f'    """Step: {step.name or step.id}"""')

        # Construir URL con variables resueltas
        url_expr = f'f\'{base_url}{req.path}\''.replace("{", "{session_vars.get('").replace("}", "', '')}\"")
        lines.append(f"    url = f\"{base_url}{req.path}\"")

        # Headers
        if req.headers:
            lines.append(f"    headers = {json.dumps(req.headers)}")
        else:
            lines.append("    headers = {}")

        # Body
        if req.body:
            lines.append(f"    body = {json.dumps(req.body)}")
            lines.append(f"    resp = httpx.{req.method.value.lower()}(url, json=body, headers=headers)")
        else:
            lines.append(f"    resp = httpx.{req.method.value.lower()}(url, headers=headers)")

        # Aserciones
        for expr in step.expect:
            if expr.startswith("status="):
                expected_status = expr.split("=")[1]
                lines.append(f"    assert resp.status_code == {expected_status}")
            elif expr.startswith("status>="):
                val = expr.split(">=")[1]
                lines.append(f"    assert resp.status_code >= {val}")
            elif expr.startswith("status<"):
                val = expr.split("<")[1]
                lines.append(f"    assert resp.status_code < {val}")

        # Save vars
        for var, path in step.save.items():
            if path.startswith("body."):
                key = path[5:]
                lines.append(f"    session_vars['{var}'] = resp.json().get('{key}')")

        lines.append("")

    return "\n".join(lines)
