"""
Proveedor de autenticación.
Pattern: Strategy — cada tipo de auth implementa AuthProvider.
"""
from __future__ import annotations

import asyncio
import base64
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx


class AuthProvider(ABC):
    @abstractmethod
    async def apply(self, request: httpx.Request) -> httpx.Request:
        """Aplica la autenticación al request."""

    async def get_token_string(self) -> str | None:
        """Para esquemas que producen un token Bearer."""
        return None


class NoAuthProvider(AuthProvider):
    async def apply(self, request: httpx.Request) -> httpx.Request:
        return request


class BearerAuthProvider(AuthProvider):
    def __init__(self, token: str) -> None:
        self._token = token

    async def apply(self, request: httpx.Request) -> httpx.Request:
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request

    async def get_token_string(self) -> str | None:
        return self._token


class ApiKeyHeaderProvider(AuthProvider):
    def __init__(self, header_name: str, value: str) -> None:
        self._name = header_name
        self._value = value

    async def apply(self, request: httpx.Request) -> httpx.Request:
        request.headers[self._name] = self._value
        return request


class ApiKeyQueryProvider(AuthProvider):
    def __init__(self, param_name: str, value: str) -> None:
        self._name = param_name
        self._value = value

    async def apply(self, request: httpx.Request) -> httpx.Request:
        # Modificar la URL añadiendo el query param
        url = request.url
        params = dict(url.params) | {self._name: self._value}
        request = request.copy_with(url=url.copy_with(params=params))
        return request


class BasicAuthProvider(AuthProvider):
    def __init__(self, user: str, password: str) -> None:
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._header = f"Basic {encoded}"

    async def apply(self, request: httpx.Request) -> httpx.Request:
        request.headers["Authorization"] = self._header
        return request


class OAuth2Provider(AuthProvider):
    """Client Credentials flow — usa authlib para token management."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def _ensure_token(self) -> None:
        if self._token and time.time() < self._expires_at - 30:
            return
        from authlib.integrations.httpx_client import AsyncOAuth2Client
        async with AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            scope=self._scope,
        ) as client:
            token = await client.fetch_token(
                self._token_url,
                grant_type="client_credentials",
            )
        self._token = token["access_token"]
        self._expires_at = time.time() + token.get("expires_in", 3600)

    async def apply(self, request: httpx.Request) -> httpx.Request:
        await self._ensure_token()
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request

    async def get_token_string(self) -> str | None:
        await self._ensure_token()
        return self._token


class OAuth2RopcProvider(AuthProvider):
    """Resource Owner Password Credentials flow — usa authlib."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        username: str,
        password: str,
        scope: str | None = None,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._username = username
        self._password = password
        self._scope = scope
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def _ensure_token(self) -> None:
        if self._token and time.time() < self._expires_at - 30:
            return
        from authlib.integrations.httpx_client import AsyncOAuth2Client
        async with AsyncOAuth2Client(
            client_id=self._client_id,
            scope=self._scope,
        ) as client:
            token = await client.fetch_token(
                self._token_url,
                grant_type="password",
                username=self._username,
                password=self._password,
            )
        self._token = token["access_token"]
        self._expires_at = time.time() + token.get("expires_in", 3600)

    async def apply(self, request: httpx.Request) -> httpx.Request:
        await self._ensure_token()
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request

    async def get_token_string(self) -> str | None:
        await self._ensure_token()
        return self._token


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def run_cmd(cmd: str) -> str:
    """Ejecuta un comando de shell y devuelve su stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Comando falló: {cmd}\n{result.stderr}")
    return result.stdout.strip()


def build_provider(auth_config: Any) -> AuthProvider:
    """Factory que construye el AuthProvider correcto desde un AuthConfig."""
    from xaip.core.models import (
        AuthType,
        BearerAuth,
        ApiKeyAuth,
        ApiKeyLocation,
        BasicAuth,
        OAuth2Auth,
        OAuth2RopcAuth,
        NoAuth,
    )

    if auth_config is None or isinstance(auth_config, NoAuth):
        return NoAuthProvider()

    if isinstance(auth_config, BearerAuth):
        token = auth_config.token
        if auth_config.token_cmd:
            token = run_cmd(auth_config.token_cmd)
        elif auth_config.token_from_var:
            import os
            token = os.environ.get(auth_config.token_from_var, "")
        return BearerAuthProvider(token or "")

    if isinstance(auth_config, ApiKeyAuth):
        value = auth_config.value
        if auth_config.value_cmd:
            value = run_cmd(auth_config.value_cmd)
        if auth_config.location == ApiKeyLocation.HEADER:
            return ApiKeyHeaderProvider(auth_config.name, value or "")
        return ApiKeyQueryProvider(auth_config.name, value or "")

    if isinstance(auth_config, BasicAuth):
        password = auth_config.password
        if auth_config.password_cmd:
            password = run_cmd(auth_config.password_cmd)
        return BasicAuthProvider(auth_config.user, password or "")

    if isinstance(auth_config, OAuth2Auth):
        secret = auth_config.client_secret
        if auth_config.client_secret_cmd:
            secret = run_cmd(auth_config.client_secret_cmd)
        return OAuth2Provider(
            auth_config.token_url,
            auth_config.client_id,
            secret or "",
            auth_config.scope,
        )

    if isinstance(auth_config, OAuth2RopcAuth):
        password = auth_config.password
        if auth_config.password_cmd:
            password = run_cmd(auth_config.password_cmd)
        return OAuth2RopcProvider(
            auth_config.token_url,
            auth_config.client_id,
            auth_config.username,
            password or "",
            auth_config.scope,
        )

    return NoAuthProvider()
