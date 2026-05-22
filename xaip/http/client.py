"""
Cliente HTTP asíncrono — wrapper sobre httpx.
Pattern: Facade
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from xaip.auth.providers import AuthProvider, NoAuthProvider


class HttpClient:
    """
    Facade sobre httpx.AsyncClient con:
    - Autenticación automática
    - Captura de tiempo
    - Respuesta normalizada como dict
    """

    def __init__(
        self,
        base_url: str = "",
        auth_provider: AuthProvider | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth_provider or NoAuthProvider()
        self._timeout = timeout
        self._follow_redirects = follow_redirects

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        body: Any = None,
        form: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> "ResponseData":
        url = self._build_url(path)
        req_headers: dict[str, str] = dict(headers or {})

        # Construir request básico para que el AuthProvider pueda modificarlo
        content: bytes | None = None
        if body is not None:
            content = json.dumps(body, ensure_ascii=False).encode()
            req_headers.setdefault("Content-Type", "application/json")

        req = httpx.Request(
            method=method.upper(),
            url=url,
            headers=req_headers,
            params=params or {},
            content=content,
        )

        # Aplicar autenticación
        req = await self._auth.apply(req)

        # Los headers explícitos del paso tienen prioridad sobre el auth provider.
        # Si el llamante pasó Authorization explícitamente, restaurarlo.
        if headers:
            explicit_auth = next(
                (v for k, v in headers.items() if k.lower() == "authorization"),
                None,
            )
            if explicit_auth:
                req.headers["authorization"] = explicit_auth

        t0 = time.monotonic()
        async with httpx.AsyncClient(
            follow_redirects=self._follow_redirects,
            timeout=timeout or self._timeout,
        ) as client:
            if form:
                # Multipart/form — reconstruir con form data
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=dict(req.headers),
                    params=params or {},
                    data=form,
                )
            else:
                resp = await client.send(req)

        duration_ms = int((time.monotonic() - t0) * 1000)

        # Parsear body
        resp_body: Any = None
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = resp.text
        else:
            resp_body = resp.text

        return ResponseData(
            status=resp.status_code,
            headers=dict(resp.headers),
            body=resp_body,
            duration_ms=duration_ms,
            raw_request=req,
        )

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"


class ResponseData:
    """Respuesta normalizada."""

    def __init__(
        self,
        status: int,
        headers: dict[str, str],
        body: Any,
        duration_ms: int,
        raw_request: httpx.Request | None = None,
    ) -> None:
        self.status = status
        self.headers = headers
        self.body = body
        self.duration_ms = duration_ms
        self.raw_request = raw_request

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ms": self.duration_ms,
            "headers": self.headers,
            "body": self.body,
        }

    def request_dict(self) -> dict[str, Any]:
        if not self.raw_request:
            return {}
        body: Any = None
        if self.raw_request.content:
            try:
                body = json.loads(self.raw_request.content)
            except Exception:
                body = self.raw_request.content.decode(errors="replace")
        return {
            "method": self.raw_request.method,
            "url": str(self.raw_request.url),
            "headers": dict(self.raw_request.headers),
            "body": body,
        }
