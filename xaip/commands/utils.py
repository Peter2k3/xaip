"""
Utilidades compartidas para todos los comandos CLI.
Pattern: Façade — oculta detalles de output y carga de config.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()
err_console = Console(stderr=True)


def load_config(config_path: str | None = None):
    """Carga el .xaip.json con manejo de errores."""
    from xaip.core.config_repo import ConfigRepository
    repo = ConfigRepository(Path(config_path) if config_path else None)
    try:
        return repo.load(), repo
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        err_console.print(f"[red]Config inválida:[/red] {exc}")
        raise typer.Exit(1) from exc


def output_json(data: Any, quiet: bool = False) -> None:
    if quiet:
        return
    print(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default))


def _json_default(obj: Any) -> Any:
    from datetime import datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def exit_with(code: int) -> None:
    raise typer.Exit(code)


def resolve_env(cfg, env_name: str | None) -> "Environment":
    from xaip.core.models import Environment
    name = env_name or cfg.active_env
    env = cfg.environments.get(name)
    if not env:
        err_console.print(f"[red]Entorno '{name}' no encontrado en .xaip.json[/red]")
        raise typer.Exit(1)
    env.name = name
    return env
