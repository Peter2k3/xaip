"""
xaip session — variables de sesión efímeras
xaip var resolve — resolución de plantillas
"""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from xaip.commands.utils import load_config, output_json
from xaip.core.resolver import VariableResolver

console = Console()

session_app = typer.Typer(help="Variables de sesión efímeras")
var_app = typer.Typer(help="Operaciones sobre variables de plantilla")

_SESSION_STORE: dict[str, str] = {}


@session_app.command("set")
def session_set(
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
) -> None:
    _SESSION_STORE[key] = value
    console.print(f"[green]{key}={value}[/green]")
    console.print("[yellow]Nota: las variables de sesión son efímeras y se pierden al salir.[/yellow]")


@session_app.command("get")
def session_get(
    key: str = typer.Argument(...),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    val = _SESSION_STORE.get(key)
    if val is None:
        console.print(f"[yellow]Variable '{key}' no definida.[/yellow]")
        raise typer.Exit(1)
    output_json({key: val}, quiet)


@session_app.command("list")
def session_list(
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    if not _SESSION_STORE:
        console.print("[yellow]Sin variables de sesión.[/yellow]")
        return
    output_json(_SESSION_STORE, quiet)


@session_app.command("clear")
def session_clear() -> None:
    _SESSION_STORE.clear()
    console.print("[green]Sesión limpiada.[/green]")


# ---------------------------------------------------------------------------
# xaip var resolve
# ---------------------------------------------------------------------------

@var_app.command("resolve")
def var_resolve(
    template: str = typer.Argument(..., help="Texto con {{env.KEY}} o {{session.KEY}}"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    active_env = cfg.get_active_env() if not env else cfg.environments.get(env)
    env_vars = active_env.vars if active_env else {}

    resolver = VariableResolver(env_vars=env_vars, session_vars=_SESSION_STORE)
    resolved = resolver.resolve(template)
    output_json({"template": template, "resolved": resolved}, quiet)
