"""
xaip — AI-Driven API Tester
Entry point: wires all command groups into one Typer app.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from xaip.commands.cmd_auth import app as auth_app
from xaip.commands.cmd_collection import app as collection_app
from xaip.commands.cmd_endpoints import app as endpoints_app
from xaip.commands.cmd_env import app as env_app
from xaip.commands.cmd_history import diff_app, history_app
from xaip.commands.cmd_import_export import export_app, import_app
from xaip.commands.cmd_init import app as init_app
from xaip.commands.cmd_scan import app as scan_app
from xaip.commands.cmd_session import session_app, var_app
from xaip.commands.cmd_utils import utils_app

console = Console()

app = typer.Typer(
    name="xaip",
    help="XAIP — AI-Driven API Tester CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── Core ────────────────────────────────────────────────────────────────────
app.add_typer(init_app, name="init")
app.add_typer(scan_app, name="scan")


@app.command("run")
def run_cmd(
    method: str = typer.Argument(..., help="Método HTTP: GET, POST, PUT, PATCH, DELETE"),
    path: str = typer.Argument(..., help="Path del endpoint, ej: /users/1"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    param: Optional[list[str]] = typer.Option(None, "--param", "-p", help="key=value"),
    header: Optional[list[str]] = typer.Option(None, "--header", "-H", help="Key: Value"),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="JSON string"),
    body_file: Optional[str] = typer.Option(None, "--body-file", help="Ruta a archivo JSON"),
    form: Optional[list[str]] = typer.Option(None, "--form", "-F", help="key=value"),
    save: Optional[list[str]] = typer.Option(None, "--save", help="var=body.field"),
    expect: Optional[list[str]] = typer.Option(None, "--expect", help="status=200"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    follow_redirects: bool = typer.Option(False, "--follow-redirects"),
    timeout: Optional[str] = typer.Option(None, "--timeout"),
    output_fmt: str = typer.Option("json", "--output", "-o"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Ejecuta una petición HTTP ad-hoc."""
    import asyncio
    import json as _json
    from xaip.auth.providers import build_provider
    from xaip.commands.utils import load_config, output_json, resolve_env
    from xaip.core.assertions import AssertionEngine
    from xaip.core.extractor import ValueExtractor
    from xaip.core.resolver import VariableResolver
    from xaip.http.client import HttpClient

    cfg, repo = load_config(config)
    active_env = resolve_env(cfg, env)

    params_dict = {k: v for kv in (param or []) for k, v in [kv.split("=", 1)] if "=" in kv}
    hdrs = {}
    for h in (header or []):
        if ": " in h:
            k, v = h.split(": ", 1)
        elif ":" in h:
            k, v = h.split(":", 1)
        else:
            continue
        hdrs[k.strip()] = v.strip()

    body_data = None
    if body:
        try:
            body_data = _json.loads(body)
        except _json.JSONDecodeError:
            body_data = body
    elif body_file:
        from pathlib import Path
        body_data = _json.loads(Path(body_file).read_text())

    resolver = VariableResolver(env_vars=active_env.vars)
    path_resolved = resolver.resolve(path)
    hdrs_resolved = {k: resolver.resolve(v) for k, v in hdrs.items()}
    params_resolved = {k: resolver.resolve(v) for k, v in params_dict.items()}
    body_resolved = resolver.resolve(body_data)

    if dry_run:
        output_json({
            "dryRun": True, "method": method.upper(),
            "url": f"{active_env.base_url.rstrip('/')}/{path_resolved.lstrip('/')}",
            "headers": hdrs_resolved, "params": params_resolved, "body": body_resolved,
        }, quiet)
        return

    timeout_secs = 30.0
    if timeout:
        from xaip.commands.cmd_run import _parse_duration
        timeout_secs = _parse_duration(timeout)

    auth = build_provider(active_env.auth)

    async def _run() -> dict:
        client = HttpClient(base_url=active_env.base_url, auth_provider=auth,
                            timeout=timeout_secs, follow_redirects=follow_redirects)
        resp = await client.request(method.upper(), path_resolved, headers=hdrs_resolved,
                                    params=params_resolved, body=body_resolved)
        engine = AssertionEngine()
        assertion_results = [
            engine.evaluate(expr, resp.status, resp.headers, resp.body, resp.duration_ms)
            for expr in (expect or [])
        ]
        extractor = ValueExtractor()
        saved = {}
        for sv in (save or []):
            if "=" in sv:
                vn, expr = sv.split("=", 1)
                saved[vn.strip()] = extractor.extract(expr.strip(), resp.body, resp.headers, resp.status)
        all_passed = all(a.passed for a in assertion_results)
        return {
            "request": resp.request_dict(), "response": resp.to_dict(),
            "assertions": [a.model_dump() for a in assertion_results],
            "saved": saved, "exitCode": 0 if all_passed else 1,
        }

    result = asyncio.run(_run())
    output_json(result, quiet)
    if result.get("exitCode", 0) != 0:
        raise typer.Exit(1)


# ── Command groups ───────────────────────────────────────────────────────────
app.add_typer(endpoints_app, name="endpoints")
app.add_typer(env_app, name="env")
app.add_typer(auth_app, name="auth")
app.add_typer(collection_app, name="collection")
app.add_typer(history_app, name="history")
app.add_typer(diff_app, name="diff")
app.add_typer(import_app, name="import")
app.add_typer(export_app, name="export")
app.add_typer(session_app, name="session")
app.add_typer(var_app, name="var")

# ── Utilities ────────────────────────────────────────────────────────────────
app.add_typer(utils_app, name="utils")


# ── Standalone utility commands (shortcuts) ──────────────────────────────────
@app.command("doctor")
def doctor_cmd() -> None:
    """Diagnóstico del entorno."""
    from xaip.commands.cmd_utils import doctor
    doctor()


@app.command("validate")
def validate_cmd(config: Optional[str] = typer.Option(None, "--config")) -> None:
    """Valida .xaip.json."""
    from xaip.commands.cmd_utils import validate
    validate(config=config)


@app.command("version")
def version_cmd() -> None:
    """Muestra la versión."""
    from xaip.commands.cmd_utils import show_version
    show_version()


@app.command("edit")
def edit_cmd(config: Optional[str] = typer.Option(None, "--config")) -> None:
    """Abre .xaip.json en el editor."""
    from xaip.commands.cmd_utils import edit
    edit(config=config)


# ── TUI ──────────────────────────────────────────────────────────────────────
@app.command("tui")
def tui_cmd(
    collection: Optional[str] = typer.Option(None, "--collection", "-c"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Abre la interfaz de texto interactiva."""
    from xaip.tui.app import XaipTUI
    tui = XaipTUI(config_path=config, env=env, collection=collection)
    tui.run()


if __name__ == "__main__":
    app()
