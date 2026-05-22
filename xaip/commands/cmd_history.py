"""
xaip history — historial de ejecuciones
xaip diff — comparación entre runs usando deepdiff
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from xaip.commands.utils import load_config, output_json

console = Console()

# ---------------------------------------------------------------------------
# xaip history
# ---------------------------------------------------------------------------
history_app = typer.Typer(help="Historial de ejecuciones")


@history_app.command("list")
def history_list(
    limit: int = typer.Option(20, "--limit", "-n"),
    collection: Optional[str] = typer.Option(None, "--collection"),
    since: Optional[str] = typer.Option(None, "--since", help="ISO date ej: 2026-05-01"),
    status: Optional[str] = typer.Option(None, "--status", help="failed | passed"),
    config: Optional[str] = typer.Option(None, "--config"),
    output_fmt: str = typer.Option("json", "--output", "-o"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    runs = list(cfg.history)

    if collection:
        runs = [r for r in runs if r.collection == collection]
    if since:
        dt = datetime.fromisoformat(since)
        runs = [r for r in runs if r.started_at >= dt]
    if status:
        if status == "failed":
            runs = [r for r in runs if r.exit_code != 0]
        elif status == "passed":
            runs = [r for r in runs if r.exit_code == 0]

    runs = runs[-limit:]

    data = [
        {
            "id": r.id,
            "collection": r.collection,
            "env": r.env,
            "startedAt": r.started_at.isoformat() if r.started_at else None,
            "duration": r.duration_ms,
            "summary": r.summary,
            "exitCode": r.exit_code,
        }
        for r in runs
    ]

    if output_fmt == "table":
        t = Table("ID", "Colección", "Env", "Fecha", "Status")
        for row in data:
            icon = "✅" if row["exitCode"] == 0 else "❌"
            t.add_row(row["id"], row["collection"] or "-", row["env"], row.get("startedAt", "")[:19], icon)
        console.print(t)
    else:
        output_json(data, quiet)


@history_app.command("show")
def history_show(
    run_id: str = typer.Argument(..., help="ID del run o 'last'"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    if not cfg.history:
        console.print("[yellow]Sin historial.[/yellow]")
        raise typer.Exit(0)

    if run_id == "last":
        run = cfg.history[-1]
    else:
        run = next((r for r in cfg.history if r.id == run_id), None)
        if not run:
            console.print(f"[red]Run '{run_id}' no encontrado.[/red]")
            raise typer.Exit(1)

    output_json(run.model_dump(by_alias=True, exclude_none=True), quiet)


@history_app.command("clear")
def history_clear(
    older_than: Optional[str] = typer.Option(None, "--older-than", help="ej: 30d"),
    all_: bool = typer.Option(False, "--all"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    if all_:
        count = len(cfg.history)
        cfg.history = []
        repo.save(cfg)
        console.print(f"[green]{count} registros eliminados.[/green]")
        return

    if older_than:
        days = _parse_days(older_than)
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        before = len(cfg.history)
        cfg.history = [r for r in cfg.history if r.started_at and r.started_at >= cutoff]
        removed = before - len(cfg.history)
        repo.save(cfg)
        console.print(f"[green]{removed} registros eliminados.[/green]")


def _parse_days(s: str) -> int:
    s = s.strip()
    if s.endswith("d"):
        return int(s[:-1])
    if s.endswith("w"):
        return int(s[:-1]) * 7
    return int(s)


# ---------------------------------------------------------------------------
# xaip diff — usa deepdiff
# ---------------------------------------------------------------------------
diff_app = typer.Typer(help="Diff entre ejecuciones")


@diff_app.callback(invoke_without_command=True)
def diff(
    run_a: Optional[str] = typer.Argument(None),
    run_b: Optional[str] = typer.Argument(None),
    collection: Optional[str] = typer.Option(None, "--collection"),
    step: Optional[str] = typer.Option(None, "--step"),
    baseline: Optional[str] = typer.Option(None, "--baseline"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)

    history = cfg.history
    if collection:
        history = [r for r in history if r.collection == collection]

    if len(history) < 2:
        console.print("[yellow]Se necesitan al menos 2 ejecuciones para hacer diff.[/yellow]")
        raise typer.Exit(0)

    # Resolver los dos runs a comparar
    if run_a and run_b:
        ra = next((r for r in history if r.id == run_a), None)
        rb = next((r for r in history if r.id == run_b), None)
    elif baseline:
        ra = next((r for r in history if r.id == baseline), None)
        rb = history[-1]
    else:
        ra = history[-2]
        rb = history[-1]

    if not ra or not rb:
        console.print("[red]No se encontraron los runs indicados.[/red]")
        raise typer.Exit(1)

    # Construir dicts a comparar
    def run_to_dict(r) -> dict:
        result = {}
        for s in r.steps:
            if step and s.id != step:
                continue
            result[s.id] = s.response or {}
        return result

    dict_a = run_to_dict(ra)
    dict_b = run_to_dict(rb)

    from deepdiff import DeepDiff
    dd = DeepDiff(dict_a, dict_b, ignore_order=True)

    output = {
        "runA": ra.id,
        "runB": rb.id,
        "changes": dd.to_dict(),
    }

    # Formato amigable — listar campos con delta numérico
    deltas = []
    for path, change in dd.get("values_changed", {}).items():
        old_val = change.get("old_value")
        new_val = change.get("new_value")
        delta_entry: dict = {"field": path, "before": old_val, "after": new_val}
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            delta_entry["delta"] = round(new_val - old_val, 4)
        deltas.append(delta_entry)

    output["deltas"] = deltas

    if not quiet:
        if deltas:
            t = Table("Campo", "Antes", "Después", "Delta")
            for d in deltas:
                t.add_row(
                    str(d["field"]),
                    str(d["before"]),
                    str(d["after"]),
                    str(d.get("delta", "")),
                )
            console.print(t)
        else:
            console.print("[green]Sin cambios detectados.[/green]")

    output_json(output, quiet)
