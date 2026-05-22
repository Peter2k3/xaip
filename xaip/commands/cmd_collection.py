"""
xaip collection — gestión completa de colecciones y pasos
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from xaip.commands.utils import load_config, output_json, resolve_env
from xaip.core.models import (
    Collection,
    CollectionStep,
    HttpMethod,
    StepRequest,
    StepStatus,
)
from xaip.core.runner import CollectionRunner

console = Console()
app = typer.Typer(help="Gestionar y ejecutar colecciones")
step_app = typer.Typer(help="Gestionar pasos de una colección")
app.add_typer(step_app, name="step")


# ---------------------------------------------------------------------------
# CRUD de colecciones
# ---------------------------------------------------------------------------

@app.command("list")
def collection_list(
    config: Optional[str] = typer.Option(None, "--config"),
    output_fmt: str = typer.Option("json", "--output", "-o"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    data = [{"id": c.id, "name": c.name, "steps": len(c.steps)} for c in cfg.collections]
    if output_fmt == "table":
        t = Table("ID", "Nombre", "Pasos")
        for c in data:
            t.add_row(c["id"], c["name"], str(c["steps"]))
        console.print(t)
    else:
        output_json(data, quiet)


@app.command("show")
def collection_show(
    name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    col = cfg.get_collection(name)
    if not col:
        console.print(f"[red]Colección '{name}' no encontrada.[/red]")
        raise typer.Exit(1)
    output_json(col.model_dump(by_alias=True, exclude_none=True), quiet)


@app.command("create")
def collection_create(
    name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    if cfg.get_collection(name):
        console.print(f"[yellow]Colección '{name}' ya existe.[/yellow]")
        raise typer.Exit(1)
    cfg.collections.append(Collection(id=name, name=name))
    repo.save(cfg)
    console.print(f"[green]Colección '{name}' creada.[/green]")


@app.command("delete")
def collection_delete(
    name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    before = len(cfg.collections)
    cfg.collections = [c for c in cfg.collections if c.id != name]
    if len(cfg.collections) == before:
        console.print(f"[red]Colección '{name}' no encontrada.[/red]")
        raise typer.Exit(1)
    repo.save(cfg)
    console.print(f"[green]Colección '{name}' eliminada.[/green]")


@app.command("rename")
def collection_rename(
    name: str = typer.Argument(...),
    new_name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(name)
    if not col:
        console.print(f"[red]Colección '{name}' no encontrada.[/red]")
        raise typer.Exit(1)
    col.id = new_name
    col.name = new_name
    repo.save(cfg)
    console.print(f"[green]Renombrada a '{new_name}'.[/green]")


@app.command("copy")
def collection_copy(
    name: str = typer.Argument(...),
    new_name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(name)
    if not col:
        console.print(f"[red]Colección '{name}' no encontrada.[/red]")
        raise typer.Exit(1)
    import copy
    new_col = copy.deepcopy(col)
    new_col.id = new_name
    new_col.name = new_name
    cfg.collections.append(new_col)
    repo.save(cfg)
    console.print(f"[green]Colección '{name}' copiada como '{new_name}'.[/green]")


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

@app.command("run")
def collection_run(
    name: str = typer.Argument(...),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    step_from: Optional[str] = typer.Option(None, "--step"),
    only: Optional[str] = typer.Option(None, "--only", help="IDs separados por coma"),
    skip: Optional[str] = typer.Option(None, "--skip", help="IDs separados por coma"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    stop_on_failure: bool = typer.Option(True, "--stop-on-failure/--continue-on-failure"),
    vars_str: Optional[str] = typer.Option(None, "--vars", help="k=v,k2=v2"),
    config: Optional[str] = typer.Option(None, "--config"),
    output_fmt: str = typer.Option("json", "--output", "-o"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(name)
    if not col:
        console.print(f"[red]Colección '{name}' no encontrada.[/red]")
        raise typer.Exit(1)

    active_env = resolve_env(cfg, env)

    if dry_run:
        _print_dry_run(col)
        return

    extra_vars: dict = {}
    if vars_str:
        for kv in vars_str.split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                extra_vars[k.strip()] = v.strip()

    only_list = [x.strip() for x in only.split(",")] if only else None
    skip_list = [x.strip() for x in skip.split(",")] if skip else None

    def on_start(step_id: str) -> None:
        if not quiet:
            console.print(f"[cyan]▶ {step_id}[/cyan]", end=" ")

    def on_end(result) -> None:
        if not quiet:
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭", "error": "💥"}.get(
                result.status.value, "?"
            )
            console.print(f"{icon} {result.duration_ms}ms")

    runner = CollectionRunner(active_env, on_step_start=on_start, on_step_end=on_end)
    run_result = asyncio.run(
        runner.run(
            col,
            stop_on_failure=stop_on_failure,
            only=only_list,
            skip=skip_list,
            from_step=step_from,
            extra_vars=extra_vars,
        )
    )

    # Persistir en historial
    cfg.history.append(run_result)
    repo.save(cfg)

    data = run_result.model_dump(by_alias=True, exclude_none=True)
    if output_fmt == "table":
        _print_run_table(run_result)
    else:
        output_json(data, quiet)

    raise typer.Exit(run_result.exit_code)


# ---------------------------------------------------------------------------
# Gestión de pasos
# ---------------------------------------------------------------------------

@step_app.command("add")
def step_add(
    collection_name: str = typer.Argument(...),
    method: str = typer.Argument(...),
    path: str = typer.Argument(...),
    step_id: Optional[str] = typer.Option(None, "--id"),
    name: Optional[str] = typer.Option(None, "--name"),
    depends_on: Optional[list[str]] = typer.Option(None, "--depends-on"),
    parallel: bool = typer.Option(False, "--parallel"),
    run_if: Optional[str] = typer.Option(None, "--run-if"),
    always: bool = typer.Option(False, "--always"),
    retry: int = typer.Option(0, "--retry"),
    retry_delay: Optional[str] = typer.Option(None, "--retry-delay"),
    retry_until: Optional[str] = typer.Option(None, "--retry-until"),
    timeout: Optional[str] = typer.Option(None, "--timeout"),
    body: Optional[str] = typer.Option(None, "--body", "-b"),
    body_file: Optional[str] = typer.Option(None, "--body-file"),
    param: Optional[list[str]] = typer.Option(None, "--param", "-p"),
    header: Optional[list[str]] = typer.Option(None, "--header", "-H"),
    save: Optional[list[str]] = typer.Option(None, "--save"),
    expect: Optional[list[str]] = typer.Option(None, "--expect"),
    as_auth: bool = typer.Option(False, "--as-auth"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        console.print(f"[red]Colección '{collection_name}' no encontrada.[/red]")
        raise typer.Exit(1)

    sid = step_id or str(uuid.uuid4())[:8]

    # Construir request
    headers_dict = _parse_headers(header or [])
    params_dict = _parse_kv(param or [])
    body_data = _parse_body(body, body_file)
    save_dict = _parse_kv(save or [])
    expect_list = list(expect or [])

    step = CollectionStep(
        id=sid,
        name=name or sid,
        dependsOn=depends_on or [],
        parallel=parallel,
        runIf=run_if,
        always=always,
        retry=retry,
        retryDelay=retry_delay,
        retryUntil=retry_until,
        timeout=timeout,
        request=StepRequest(
            method=HttpMethod(method.upper()),
            path=path,
            headers=headers_dict,
            params=params_dict,
            body=body_data,
            bodyFile=body_file,
        ),
        expect=expect_list,
        save=save_dict,
        asAuth=as_auth,
    )
    col.steps.append(step)
    repo.save(cfg)
    console.print(f"[green]Paso '{sid}' añadido a '{collection_name}'.[/green]")


@step_app.command("list")
def step_list(
    collection_name: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
    output_fmt: str = typer.Option("table", "--output", "-o"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        console.print(f"[red]Colección '{collection_name}' no encontrada.[/red]")
        raise typer.Exit(1)
    data = [s.model_dump(by_alias=True, exclude_none=True) for s in col.steps]
    if output_fmt == "table":
        t = Table("ID", "Nombre", "Método", "Path", "Depends On")
        for s in col.steps:
            t.add_row(s.id, s.name or "", s.request.method.value, s.request.path, ",".join(s.depends_on))
        console.print(t)
    else:
        output_json(data, quiet)


@step_app.command("remove")
def step_remove(
    collection_name: str = typer.Argument(...),
    step_id: str = typer.Argument(...),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        raise typer.Exit(1)
    before = len(col.steps)
    col.steps = [s for s in col.steps if s.id != step_id]
    if len(col.steps) == before:
        console.print(f"[red]Paso '{step_id}' no encontrado.[/red]")
        raise typer.Exit(1)
    repo.save(cfg)
    console.print(f"[green]Paso '{step_id}' eliminado.[/green]")


@step_app.command("move")
def step_move(
    collection_name: str = typer.Argument(...),
    step_id: str = typer.Argument(...),
    after: Optional[str] = typer.Option(None, "--after"),
    before_id: Optional[str] = typer.Option(None, "--before"),
    first: bool = typer.Option(False, "--first"),
    last: bool = typer.Option(False, "--last"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        raise typer.Exit(1)

    step = next((s for s in col.steps if s.id == step_id), None)
    if not step:
        console.print(f"[red]Paso '{step_id}' no encontrado.[/red]")
        raise typer.Exit(1)

    col.steps = [s for s in col.steps if s.id != step_id]

    if first:
        col.steps.insert(0, step)
    elif last:
        col.steps.append(step)
    elif after:
        idx = next((i for i, s in enumerate(col.steps) if s.id == after), -1)
        col.steps.insert(idx + 1, step)
    elif before_id:
        idx = next((i for i, s in enumerate(col.steps) if s.id == before_id), 0)
        col.steps.insert(idx, step)
    else:
        col.steps.append(step)

    repo.save(cfg)
    console.print(f"[green]Paso '{step_id}' reubicado.[/green]")


@step_app.command("edit")
def step_edit(
    collection_name: str = typer.Argument(...),
    step_id: str = typer.Argument(...),
    name: Optional[str] = typer.Option(None, "--name"),
    body: Optional[str] = typer.Option(None, "--body"),
    expect: Optional[list[str]] = typer.Option(None, "--expect"),
    save: Optional[list[str]] = typer.Option(None, "--save"),
    run_if: Optional[str] = typer.Option(None, "--run-if"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    col = cfg.get_collection(collection_name)
    if not col:
        raise typer.Exit(1)
    step = next((s for s in col.steps if s.id == step_id), None)
    if not step:
        console.print(f"[red]Paso '{step_id}' no encontrado.[/red]")
        raise typer.Exit(1)
    if name is not None:
        step.name = name
    if body is not None:
        step.request.body = _parse_body(body, None)
    if expect is not None:
        step.expect = list(expect)
    if save is not None:
        step.save = _parse_kv(save)
    if run_if is not None:
        step.run_if = run_if
    repo.save(cfg)
    console.print(f"[green]Paso '{step_id}' actualizado.[/green]")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _parse_kv(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_headers(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if ": " in item:
            k, v = item.split(": ", 1)
            result[k.strip()] = v.strip()
        elif ":" in item:
            k, v = item.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_body(body: str | None, body_file: str | None) -> object | None:
    if body:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body
    if body_file:
        from pathlib import Path
        return json.loads(Path(body_file).read_text())
    return None


def _print_dry_run(col: Collection) -> None:
    console.print(f"[bold]Colección:[/bold] {col.id}")
    t = Table("Orden", "ID", "Método", "Path", "Depends On", "Condición")
    for i, s in enumerate(col.steps, 1):
        t.add_row(
            str(i), s.id, s.request.method.value, s.request.path,
            ",".join(s.depends_on), s.run_if or ""
        )
    console.print(t)


def _print_run_table(run_result) -> None:
    t = Table("ID", "Status", "ms", "Assertions")
    for s in run_result.steps:
        icon = {"passed": "✅", "failed": "❌", "skipped": "⏭", "error": "💥"}.get(s.status.value, "?")
        assertions_str = f"{sum(1 for a in s.assertions if a.passed)}/{len(s.assertions)}"
        t.add_row(s.id, f"{icon} {s.status.value}", str(s.duration_ms), assertions_str)
    console.print(t)
    console.print(f"[bold]Resumen:[/bold] {run_result.summary}")
