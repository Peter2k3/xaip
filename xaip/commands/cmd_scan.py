"""
xaip scan — re-escanea controllers y actualiza endpoints
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from xaip.commands.utils import load_config, output_json
from xaip.scanners import detect_stack, get_scanner

console = Console()
app = typer.Typer(help="Escanear endpoints del proyecto")


@app.callback(invoke_without_command=True)
def scan(
    stack: Optional[str] = typer.Option(None, "--stack"),
    diff: bool = typer.Option(False, "--diff", help="Mostrar solo cambios"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    cfg, repo = load_config(config)
    root = repo.path.parent

    scanner = get_scanner(stack) if stack else detect_stack(root)
    if not scanner:
        console.print("[red]No se detectó stack. Usa --stack para forzar.[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Escaneando con stack: {scanner.name}[/cyan]")
    new_endpoints = scanner.scan(root)

    old_ids = {e.id for e in cfg.endpoints}
    new_ids = {e.id for e in new_endpoints}

    added = new_ids - old_ids
    removed = old_ids - new_ids
    # Modificados: misma id pero path cambió
    modified = {
        e.id for e in new_endpoints
        if e.id in old_ids
        and e.path != next((x.path for x in cfg.endpoints if x.id == e.id), e.path)
    }

    from datetime import datetime
    cfg.endpoints = new_endpoints
    cfg.scanned_at = datetime.utcnow().isoformat()
    repo.save(cfg)

    controllers = list({e.controller for e in new_endpoints if e.controller})
    result = {
        "scanned": len(new_endpoints),
        "new": len(added),
        "modified": len(modified),
        "removed": len(removed),
        "controllers": controllers,
    }

    if diff:
        result["added"] = list(added)
        result["removedIds"] = list(removed)

    if not quiet:
        console.print(f"[green]✅ {result['scanned']} endpoints ({result['new']} nuevos, {result['modified']} modificados, {result['removed']} eliminados)[/green]")

    output_json(result, quiet)
