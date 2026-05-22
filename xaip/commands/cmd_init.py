"""
xaip init — inicializa el workspace con .xaip.json
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm

from xaip.core.config_repo import ConfigRepository
from xaip.core.models import XaipConfig, Environment, NoAuth
from xaip.scanners import detect_stack, get_scanner, list_stacks
from xaip.commands.utils import output_json

console = Console()
app = typer.Typer(help="Inicializar workspace XAIP")


@app.callback(invoke_without_command=True)
def init(
    base_url: Optional[str] = typer.Option(None, "--base-url", "-u", help="URL base de la API"),
    stack: Optional[str] = typer.Option(None, "--stack", "-s", help="Stack forzado (spring-boot, fastapi...)"),
    spec: Optional[str] = typer.Option(None, "--spec", help="Ruta o URL a spec OpenAPI"),
    config: Optional[str] = typer.Option(None, "--config", help="Ruta alternativa para .xaip.json"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    root = Path.cwd()
    repo = ConfigRepository(Path(config) if config else root / ".xaip.json")

    if repo.exists():
        if not Confirm.ask("[yellow].xaip.json ya existe. ¿Sobreescribir?[/yellow]"):
            raise typer.Exit(0)

    # Determinar stack
    scanner = None
    if stack:
        scanner = get_scanner(stack)
        if not scanner:
            console.print(f"[red]Stack desconocido: {stack}. Disponibles: {', '.join(list_stacks())}[/red]")
            raise typer.Exit(1)
    elif not spec:
        scanner = detect_stack(root)
        if scanner:
            console.print(f"[green]Stack detectado:[/green] {scanner.name}")
        else:
            console.print("[yellow]No se detectó stack automáticamente.[/yellow]")

    # Pedir baseUrl si no se pasó
    if not base_url and not quiet:
        base_url = Prompt.ask("baseUrl del entorno dev", default="http://localhost:8080/api/v1")
    base_url = base_url or "http://localhost:8080/api/v1"

    # Nombre del proyecto
    project_name = root.name

    # Crear config base
    cfg = XaipConfig(
        project=project_name,
        version="1",
        activeEnv="dev",
        environments={
            "dev": Environment(
                name="dev",
                baseUrl=base_url,
                auth=NoAuth(),
                vars={},
            )
        },
        endpoints=[],
        collections=[],
        history=[],
    )

    # Escanear si hay scanner
    if scanner and not spec:
        console.print(f"[cyan]Escaneando endpoints ({scanner.name})...[/cyan]")
        endpoints = scanner.scan(root)
        cfg.endpoints = endpoints
        console.print(f"[green]Encontrados {len(endpoints)} endpoints[/green]")
    elif spec:
        cfg.endpoints = _load_spec(spec)
        console.print(f"[green]Importados {len(cfg.endpoints)} endpoints desde spec[/green]")

    repo.save(cfg)
    console.print(f"[green]✅ .xaip.json creado en {repo.path}[/green]")

    output_json({
        "project": project_name,
        "activeEnv": "dev",
        "endpoints": len(cfg.endpoints),
        "configPath": str(repo.path),
    }, quiet)


def _load_spec(spec: str) -> list:
    import asyncio
    from xaip.scanners.openapi import OpenApiScanner
    scanner_oa = OpenApiScanner()
    if spec.startswith("http://") or spec.startswith("https://"):
        return asyncio.run(scanner_oa.load_from_url(spec))
    return scanner_oa.load_from_file(Path(spec))
