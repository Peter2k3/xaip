"""
xaip auth — configuración y prueba de autenticación por entorno
"""
from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

from xaip.auth.providers import build_provider
from xaip.commands.utils import load_config, output_json, resolve_env
from xaip.core.models import (
    ApiKeyAuth,
    ApiKeyLocation,
    AuthType,
    BasicAuth,
    BearerAuth,
    NoAuth,
    OAuth2Auth,
    OAuth2RopcAuth,
)

console = Console()
app = typer.Typer(help="Gestionar autenticación")
set_app = typer.Typer(help="Configurar esquema de auth")
app.add_typer(set_app, name="set")


@app.command("show")
def auth_show(
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    active_env = resolve_env(cfg, env)
    auth = active_env.auth
    if auth is None:
        data = {"type": "none"}
    else:
        data = auth.model_dump(by_alias=True, exclude_none=True)
        # Ocultar secrets
        for field in ("token", "password", "clientSecret"):
            if field in data:
                data[field] = "***"
    output_json(data, quiet)


@set_app.command("bearer")
def set_bearer(
    token: Optional[str] = typer.Option(None, "--token"),
    token_cmd: Optional[str] = typer.Option(None, "--token-cmd"),
    token_from_var: Optional[str] = typer.Option(None, "--token-from-var"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    active_env = resolve_env(cfg, env)
    env_name = env or cfg.active_env
    cfg.environments[env_name].auth = BearerAuth(
        token=token,
        tokenCmd=token_cmd,
        tokenFromVar=token_from_var,
    )
    repo.save(cfg)
    console.print(f"[green]Auth bearer configurada para entorno '{env_name}'.[/green]")


@set_app.command("apikey")
def set_apikey(
    header: Optional[str] = typer.Option(None, "--header", help="Nombre del header"),
    query: Optional[str] = typer.Option(None, "--query", help="Nombre del query param"),
    value: Optional[str] = typer.Option(None, "--value"),
    value_cmd: Optional[str] = typer.Option(None, "--value-cmd"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env_name = env or cfg.active_env
    if not header and not query:
        console.print("[red]Debes especificar --header o --query[/red]")
        raise typer.Exit(1)
    location = ApiKeyLocation.HEADER if header else ApiKeyLocation.QUERY
    name = header or query
    cfg.environments[env_name].auth = ApiKeyAuth(
        location=location, name=name, value=value, valueCmd=value_cmd
    )
    repo.save(cfg)
    console.print(f"[green]Auth apikey configurada en '{env_name}'.[/green]")


@set_app.command("basic")
def set_basic(
    user: str = typer.Option(..., "--user"),
    password: Optional[str] = typer.Option(None, "--password"),
    password_cmd: Optional[str] = typer.Option(None, "--password-cmd"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env_name = env or cfg.active_env
    cfg.environments[env_name].auth = BasicAuth(
        user=user, password=password, passwordCmd=password_cmd
    )
    repo.save(cfg)
    console.print(f"[green]Auth basic configurada en '{env_name}'.[/green]")


@set_app.command("oauth2")
def set_oauth2(
    token_url: str = typer.Option(..., "--token-url"),
    client_id: str = typer.Option(..., "--client-id"),
    client_secret: Optional[str] = typer.Option(None, "--client-secret"),
    client_secret_cmd: Optional[str] = typer.Option(None, "--client-secret-cmd"),
    scope: Optional[str] = typer.Option(None, "--scope"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env_name = env or cfg.active_env
    cfg.environments[env_name].auth = OAuth2Auth(
        tokenUrl=token_url,
        clientId=client_id,
        clientSecret=client_secret,
        clientSecretCmd=client_secret_cmd,
        scope=scope,
    )
    repo.save(cfg)
    console.print(f"[green]Auth oauth2 configurada en '{env_name}'.[/green]")


@set_app.command("oauth2-ropc")
def set_oauth2_ropc(
    token_url: str = typer.Option(..., "--token-url"),
    client_id: str = typer.Option(..., "--client-id"),
    username: str = typer.Option(..., "--username"),
    password: Optional[str] = typer.Option(None, "--password"),
    password_cmd: Optional[str] = typer.Option(None, "--password-cmd"),
    scope: Optional[str] = typer.Option(None, "--scope"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env_name = env or cfg.active_env
    cfg.environments[env_name].auth = OAuth2RopcAuth(
        tokenUrl=token_url,
        clientId=client_id,
        username=username,
        password=password,
        passwordCmd=password_cmd,
        scope=scope,
    )
    repo.save(cfg)
    console.print(f"[green]Auth oauth2-ropc configurada en '{env_name}'.[/green]")


@app.command("none")
def auth_none(
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    cfg, repo = load_config(config)
    env_name = env or cfg.active_env
    cfg.environments[env_name].auth = NoAuth()
    repo.save(cfg)
    console.print(f"[green]Auth eliminada en '{env_name}'.[/green]")


@app.command("test")
def auth_test(
    endpoint: Optional[str] = typer.Option(None, "--endpoint", help="ej: GET /me"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    cfg, _ = load_config(config)
    active_env = resolve_env(cfg, env)
    provider = build_provider(active_env.auth)

    async def _test() -> dict:
        token = await provider.get_token_string()
        if token:
            result = {"status": "ok", "tokenPreview": token[:20] + "..."}
        else:
            result = {"status": "ok", "type": "no-token-auth"}

        if endpoint:
            from xaip.http.client import HttpClient
            parts = endpoint.strip().split(" ", 1)
            method, path = (parts[0], parts[1]) if len(parts) == 2 else ("GET", endpoint)
            client = HttpClient(base_url=active_env.base_url, auth_provider=provider)
            resp = await client.request(method, path)
            result["probe"] = resp.to_dict()
        return result

    data = asyncio.run(_test())
    output_json(data, quiet)


@app.command("refresh")
def auth_refresh(
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    config: Optional[str] = typer.Option(None, "--config"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Fuerza la renovación del token."""
    cfg, _ = load_config(config)
    active_env = resolve_env(cfg, env)
    provider = build_provider(active_env.auth)

    # Limpiar cache interno — llamar _ensure_token con expires_at = 0
    if hasattr(provider, "_expires_at"):
        provider._expires_at = 0.0

    async def _refresh() -> str | None:
        return await provider.get_token_string()

    token = asyncio.run(_refresh())
    if token:
        console.print("[green]Token renovado.[/green]")
        output_json({"refreshed": True, "tokenPreview": token[:20] + "..."}, quiet)
    else:
        console.print("[yellow]No se obtuvo token (auth sin token).[/yellow]")
