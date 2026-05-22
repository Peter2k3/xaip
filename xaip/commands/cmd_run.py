"""
xaip run — ejecuta un request único
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import typer
from rich.console import Console

from xaip.auth.providers import build_provider
from xaip.commands.utils import load_config, output_json, resolve_env
from xaip.core.assertions import AssertionEngine
from xaip.core.extractor import ValueExtractor
from xaip.core.models import HttpMethod, StepResult, StepStatus, RunResult
from xaip.core.resolver import VariableResolver
from xaip.http.client import HttpClient

console = Console()
app = typer.Typer(help="Ejecutar un request HTTP")


@app.callback(invoke_without_command=True)
def run(
    method: str = typer.Argument(..., help="Método HTTP: GET, POST, PUT, DELETE..."),
    path: str = typer.Argument(..., help="Path del endpoint (ej: /catalogo/cuentas)"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    param: Optional[list[str]] = typer.Option(None, "--param", "-p", help="Query param k=v"),
    header: Optional[list[str]] = typer.Option(None, "--header", "-H", help="Header 'K: V'"),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="Body JSON inline"),
    body_file: Optional[str] = typer.Option(None, "--body-file", help="Body desde archivo"),
    form: Optional[list[str]] = typer.Option(None, "--form", "-F", help="Form field k=@file o k=v"),
    save: Optional[list[str]] = typer.Option(None, "--save", help="var=jsonpath"),
    expect: Optional[list[str]] = typer.Option(None, "--expect", help="Aserción ej: status=200"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Mostrar request sin ejecutar"),
    follow_redirects: bool = typer.Option(False, "--follow-redirects"),
    timeout_str: Optional[str] = typer.Option(None, "--timeout", help="ej: 30s, 500ms"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    output_fmt: str = typer.Option("json", "--output", "-o"),
) -> None:
    cfg, repo = load_config(config)
    active_env = resolve_env(cfg, env)

    # Parsear parámetros
    params = _parse_kv_list(param or [])
    headers_dict = _parse_header_list(header or [])
    form_dict = _parse_form_list(form or []) if form else None

    # Cargar body
    body_data: Any = None
    if body:
        try:
            body_data = json.loads(body)
        except json.JSONDecodeError:
            body_data = body
    elif body_file:
        import pathlib
        body_data = json.loads(pathlib.Path(body_file).read_text())

    # Resolver variables
    resolver = VariableResolver(env_vars=active_env.vars)
    path_resolved = resolver.resolve(path)
    headers_resolved = {k: resolver.resolve(v) for k, v in headers_dict.items()}
    params_resolved = {k: resolver.resolve(v) for k, v in params.items()}
    body_resolved = resolver.resolve(body_data)

    if dry_run:
        output_json({
            "dryRun": True,
            "method": method.upper(),
            "url": f"{active_env.base_url.rstrip('/')}/{path_resolved.lstrip('/')}",
            "headers": headers_resolved,
            "params": params_resolved,
            "body": body_resolved,
        }, quiet)
        return

    timeout = _parse_duration(timeout_str) if timeout_str else 30.0
    auth = build_provider(active_env.auth)

    async def _run() -> dict:
        client = HttpClient(
            base_url=active_env.base_url,
            auth_provider=auth,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )
        resp = await client.request(
            method.upper(),
            path_resolved,
            headers=headers_resolved,
            params=params_resolved,
            body=body_resolved,
            form=form_dict,
        )

        # Aserciones
        engine = AssertionEngine()
        assertion_results = [
            engine.evaluate(expr, resp.status, resp.headers, resp.body, resp.duration_ms)
            for expr in (expect or [])
        ]

        # Save vars
        extractor = ValueExtractor()
        saved: dict[str, Any] = {}
        for sv in (save or []):
            if "=" in sv:
                var_name, expr = sv.split("=", 1)
                saved[var_name.strip()] = extractor.extract(expr.strip(), resp.body, resp.headers, resp.status)

        all_passed = all(a.passed for a in assertion_results)

        return {
            "command": "run",
            "request": resp.request_dict(),
            "response": resp.to_dict(),
            "assertions": [a.model_dump() for a in assertion_results],
            "saved": saved,
            "exitCode": 0 if all_passed else 1,
        }

    result = asyncio.run(_run())

    if output_fmt == "table":
        _print_table(result)
    else:
        output_json(result, quiet)

    exit_code = result.get("exitCode", 0)
    if exit_code != 0:
        raise typer.Exit(exit_code)


def _parse_kv_list(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_header_list(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if ": " in item:
            k, v = item.split(": ", 1)
            result[k.strip()] = v.strip()
        elif ":" in item:
            k, v = item.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_form_list(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_duration(d: str) -> float:
    d = d.strip()
    if d.endswith("ms"):
        return float(d[:-2]) / 1000
    if d.endswith("m"):
        return float(d[:-1]) * 60
    if d.endswith("s"):
        return float(d[:-1])
    return float(d)


def _print_table(result: dict) -> None:
    from rich.table import Table
    resp = result.get("response", {})
    console.print(f"[bold]Status:[/bold] {resp.get('status')}  [bold]ms:[/bold] {resp.get('ms')}")
    assertions = result.get("assertions", [])
    if assertions:
        t = Table("Aserción", "Resultado")
        for a in assertions:
            icon = "✅" if a["passed"] else "❌"
            t.add_row(a["expr"], f"{icon} {a.get('message', '')}")
        console.print(t)
