"""
xaip env — gestión de entornos y variables
xaip session — variables de sesión temporales
xaip var — resolución de variables
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from xaip.commands.utils import load_config, output_json
from xaip.core.models import Environment, NoAuth

console = Console()

# ---------------------------------------------------------------------------
# xaip env
# ---------------------------------------------------------------------------

app = typer.Typer(help="Gestionar entornos")
var_app = typer.Typer(help="Variables de entorno")
app.add_typer(var_app, name="var")


@app.command("list")
def env_list(
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    envs = [
        {"name": k, "baseUrl": v.base_url, "active": k == cfg.active_env}
        for k, v in cfg.environments.items()
    ]
    if not quiet:
        t = Table("Nombre", "Base URL", "Activo")
        for e in envs:
            t.add_row(e["name"], e["baseUrl"], "✅" if e["active"] else "")
        console.print(t)
    output_json(envs, quiet)


@app.command("show")
def env_show(
    name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    env = cfg.environments.get(name)
    if not env:
        console.print(f"[red]Entorno '{name}' no encontrado.[/red]")
        raise typer.Exit(1)
    data = env.model_dump(by_alias=True, exclude_none=True)
    output_json(data, quiet)


@app.command("create")
def env_create(
    name: str = typer.Argument(...),
    base_url: str = typer.Option(..., "--base-url", "-u"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, repo = load_config(config)
    if name in cfg.environments:
        console.print(f"[yellow]Entorno '{name}' ya existe.[/yellow]")
        raise typer.Exit(1)
    cfg.environments[name] = Environment(name=name, baseUrl=base_url, auth=NoAuth())
    repo.save(cfg)
    console.print(f"[green]Entorno '{name}' creado.[/green]")
    output_json({"name": name, "baseUrl": base_url}, quiet)


@app.command("delete")
def env_delete(
    name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    if name not in cfg.environments:
        console.print(f"[red]Entorno '{name}' no encontrado.[/red]")
        raise typer.Exit(1)
    del cfg.environments[name]
    repo.save(cfg)
    console.print(f"[green]Entorno '{name}' eliminado.[/green]")


@app.command("set")
def env_set(
    name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, repo = load_config(config)
    if name not in cfg.environments:
        console.print(f"[red]Entorno '{name}' no encontrado.[/red]")
        raise typer.Exit(1)
    cfg.active_env = name
    repo.save(cfg)
    if not quiet:
        console.print(f"[green]Entorno activo: {name}[/green]")
    output_json({"activeEnv": name}, quiet)


# ---------------------------------------------------------------------------
# xaip env var
# ---------------------------------------------------------------------------

@var_app.command("set")
def var_set(
    env_name: str = typer.Argument(...),
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env = cfg.environments.get(env_name)
    if not env:
        console.print(f"[red]Entorno '{env_name}' no encontrado.[/red]")
        raise typer.Exit(1)
    env.vars[key] = value
    repo.save(cfg)
    console.print(f"[green]{env_name}.{key} = {value}[/green]")


@var_app.command("get")
def var_get(
    env_name: str = typer.Argument(...),
    key: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, _ = load_config(config)
    env = cfg.environments.get(env_name)
    if not env:
        raise typer.Exit(1)
    value = env.vars.get(key)
    if value is None:
        console.print(f"[yellow]Variable '{key}' no encontrada en entorno '{env_name}'[/yellow]")
        raise typer.Exit(1)
    print(value)


@var_app.command("list")
def var_list(
    env_name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    env = cfg.environments.get(env_name)
    if not env:
        raise typer.Exit(1)
    output_json(env.vars, quiet)


@var_app.command("delete")
def var_delete(
    env_name: str = typer.Argument(...),
    key: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env = cfg.environments.get(env_name)
    if not env or key not in env.vars:
        console.print(f"[red]Variable '{key}' no encontrada.[/red]")
        raise typer.Exit(1)
    del env.vars[key]
    repo.save(cfg)
    console.print(f"[green]Variable '{key}' eliminada de entorno '{env_name}'[/green]")
