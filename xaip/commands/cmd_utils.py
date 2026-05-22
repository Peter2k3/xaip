"""
Comandos utilitarios:
  xaip doctor
  xaip validate
  xaip fixture
  xaip edit
  xaip version
"""
from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

utils_app = typer.Typer(help="Utilidades diversas")

_VERSION = "0.1.0"


@utils_app.command("version")
def show_version() -> None:
    console.print(f"xaip v{_VERSION}")


@utils_app.command("doctor")
def doctor(
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Diagnóstico del entorno y configuración."""
    checks: list[tuple[str, bool, str]] = []

    # Python version
    major, minor = sys.version_info[:2]
    ok = major >= 3 and minor >= 11
    checks.append(("Python >= 3.11", ok, f"Python {major}.{minor}"))

    # Paquetes opcionales
    for pkg, import_name in [
        ("httpx", "httpx"),
        ("typer", "typer"),
        ("pydantic", "pydantic"),
        ("authlib", "authlib"),
        ("javalang", "javalang"),
        ("textual", "textual"),
        ("deepdiff", "deepdiff"),
        ("jsonpath_ng", "jsonpath_ng"),
    ]:
        try:
            m = __import__(import_name)
            ver = getattr(m, "__version__", "ok")
            checks.append((f"Paquete: {pkg}", True, ver))
        except ImportError:
            checks.append((f"Paquete: {pkg}", False, "no instalado"))

    # Config
    if config:
        from pathlib import Path
        path_ok = Path(config).exists()
        checks.append(("Config file", path_ok, config if path_ok else "no encontrado"))
    else:
        from xaip.core.config_repo import ConfigRepository
        try:
            repo = ConfigRepository()
            cfg_path = repo._find_config()
            checks.append((".xaip.json", cfg_path is not None, str(cfg_path or "no encontrado")))
        except Exception:
            checks.append((".xaip.json", False, "error al buscar"))

    t = Table("Check", "Estado", "Info")
    all_ok = True
    for name, ok_, info in checks:
        icon = "✅" if ok_ else "❌"
        t.add_row(name, icon, info)
        if not ok_:
            all_ok = False

    console.print(t)
    if not all_ok:
        raise typer.Exit(1)


@utils_app.command("validate")
def validate(
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Valida el archivo .xaip.json contra el schema Pydantic."""
    from xaip.commands.utils import load_config, output_json
    cfg, _ = load_config(config)

    errors: list[str] = []

    # Validar que los endpoints referenciados en colecciones existen
    ep_ids = {e.id for e in cfg.endpoints}
    col_count = 0
    for col in cfg.collections:
        for step in col.steps:
            col_count += 1
            for dep in step.depends_on:
                if not any(s.id == dep for s in col.steps):
                    errors.append(f"Colección '{col.id}', paso '{step.id}': dependencia '{dep}' no existe")

    # Validar entornos
    if cfg.active_env and cfg.active_env not in cfg.environments:
        errors.append(f"active_env='{cfg.active_env}' no existe en environments")

    result = {
        "valid": len(errors) == 0,
        "endpoints": len(cfg.endpoints),
        "collections": len(cfg.collections),
        "steps": col_count,
        "environments": len(cfg.environments),
        "errors": errors,
    }

    if not quiet:
        if errors:
            for e in errors:
                console.print(f"[red]✗ {e}[/red]")
        else:
            console.print("[green]✅ Configuración válida.[/green]")

    output_json(result, quiet)
    if errors:
        raise typer.Exit(1)


@utils_app.command("fixture")
def fixture(
    endpoint_id: str = typer.Argument(..., help="ID del endpoint"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Genera un payload de ejemplo para un endpoint."""
    from xaip.commands.utils import load_config, output_json
    cfg, _ = load_config(config)

    ep = cfg.get_endpoint(endpoint_id)
    if not ep:
        console.print(f"[red]Endpoint '{endpoint_id}' no encontrado.[/red]")
        raise typer.Exit(1)

    fixture_data: dict = {}
    for param in ep.parameters or []:
        fixture_data[param.name] = _fixture_value(param.type)

    if not quiet:
        import json as _json
        console.print_json(_json.dumps(fixture_data))

    output_json(fixture_data, quiet)


def _fixture_value(type_hint: str | None) -> object:
    map_: dict[str, object] = {
        "string": "example",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "array": [],
        "object": {},
    }
    return map_.get((type_hint or "string").lower(), "example")


@utils_app.command("edit")
def edit(
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Abre el archivo .xaip.json en el editor del sistema."""
    import os
    from xaip.core.config_repo import ConfigRepository
    repo = ConfigRepository(config)
    path = repo._find_config()
    if not path:
        console.print("[red].xaip.json no encontrado.[/red]")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    os.execvp(editor, [editor, str(path)])
