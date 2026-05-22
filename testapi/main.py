"""
XAIP Test API — servidor FastAPI para probar todas las features de XAIP en ambiente real.

Endpoints disponibles:
  POST /auth/token           — obtiene Bearer token
  GET  /health               — health check (sin auth)
  GET  /echo                 — refleja headers y query params
  POST /echo                 — refleja el body
  GET  /slow                 — respuesta lenta configurable (?ms=N)
  GET  /error/{code}         — fuerza un código de error específico

  — Usuarios (requieren Bearer o API-Key) —
  GET    /users              — lista usuarios (paginado)
  POST   /users              — crea usuario
  GET    /users/{id}         — obtiene usuario
  PUT    /users/{id}         — reemplaza usuario
  PATCH  /users/{id}         — actualiza campos
  DELETE /users/{id}         — elimina usuario

  — Posts (anidados) —
  GET    /users/{id}/posts   — posts de un usuario
  POST   /users/{id}/posts   — crea post
  GET    /posts              — todos los posts (paginado)
  GET    /posts/{id}         — obtiene post
  DELETE /posts/{id}         — elimina post

  — Auth básica —
  GET    /protected/basic    — requiere Basic Auth (admin:secret)
  GET    /protected/apikey   — requiere header X-Api-Key: testkey-12345

Cómo ejecutar:
  pip install fastapi uvicorn[standard]
  uvicorn testapi.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials, OAuth2PasswordBearer
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="XAIP Test API",
    description="API de prueba para ejercitar todas las features de XAIP",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

VALID_API_KEY = "testkey-12345"
STATIC_TOKEN = "test-token-static-12345"
_issued_tokens: dict[str, datetime] = {STATIC_TOKEN: datetime.now(timezone.utc) + timedelta(hours=24)}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
basic_scheme = HTTPBasic(auto_error=False)


def require_bearer(token: str | None = Depends(oauth2_scheme)) -> str:
    if token and token in _issued_tokens:
        if _issued_tokens[token] > datetime.now(timezone.utc):
            return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_api_key(x_api_key: str | None = Header(None, alias="X-Api-Key")) -> str:
    if x_api_key == VALID_API_KEY:
        return x_api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API Key inválida",
    )


def flexible_auth(
    token: str | None = Depends(oauth2_scheme),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    """Acepta Bearer token O API Key."""
    if token and token in _issued_tokens:
        if _issued_tokens[token] > datetime.now(timezone.utc):
            return f"bearer:{token[:10]}"
    if x_api_key == VALID_API_KEY:
        return f"apikey:{x_api_key[:8]}"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Se requiere Bearer token o X-Api-Key válidos",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# In-memory DB
# ---------------------------------------------------------------------------

_users: dict[int, dict] = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com", "role": "admin", "active": True},
    2: {"id": 2, "name": "Bob",   "email": "bob@example.com",   "role": "user",  "active": True},
    3: {"id": 3, "name": "Carol", "email": "carol@example.com", "role": "user",  "active": False},
}
_posts: dict[int, dict] = {
    1: {"id": 1, "user_id": 1, "title": "Hola XAIP", "body": "Mi primer post", "published": True},
    2: {"id": 2, "user_id": 1, "title": "Testing APIs", "body": "Cómo testear APIs", "published": True},
    3: {"id": 3, "user_id": 2, "title": "Draft post", "body": "...", "published": False},
}
_next_user_id = 4
_next_post_id = 4


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class TokenRequest(BaseModel):
    username: str
    password: str
    grant_type: str = "password"


class UserCreate(BaseModel):
    name: str
    email: str
    role: str = "user"


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    active: bool | None = None


class PostCreate(BaseModel):
    title: str
    body: str
    published: bool = False


class PaginatedResponse(BaseModel):
    data: list[Any]
    page: int
    limit: int
    total: int
    has_next: bool


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/auth/token", response_model=TokenResponse, tags=["auth"])
async def get_token(payload: TokenRequest) -> TokenResponse:
    """
    Obtiene un Bearer token.
    Credenciales válidas: admin/secret, user/pass123
    """
    valid = {
        "admin": "secret",
        "user": "pass123",
        "alice": "alice123",
    }
    if valid.get(payload.username) != payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )
    token = f"tok-{secrets.token_hex(16)}"
    _issued_tokens[token] = datetime.now(timezone.utc) + timedelta(hours=1)
    return TokenResponse(access_token=token)


@app.post("/auth/oauth2/token", tags=["auth"])
async def oauth2_token(
    grant_type: str = Query(...),
    client_id: str = Query(...),
    client_secret: str | None = Query(None),
    username: str | None = Query(None),
    password: str | None = Query(None),
    scope: str | None = Query(None),
) -> dict:
    """
    Endpoint OAuth2 compatible (client_credentials y password).
    client_id=xaip-client, client_secret=xaip-secret
    """
    if client_id != "xaip-client" or client_secret != "xaip-secret":
        raise HTTPException(400, "client inválido")

    if grant_type == "client_credentials":
        pass
    elif grant_type == "password":
        if username != "admin" or password != "secret":
            raise HTTPException(400, "credenciales inválidas")
    else:
        raise HTTPException(400, f"grant_type no soportado: {grant_type}")

    token = f"oauth2-{secrets.token_hex(16)}"
    _issued_tokens[token] = datetime.now(timezone.utc) + timedelta(hours=1)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
        "scope": scope or "read write",
    }


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

@app.get("/health", tags=["utils"])
async def health() -> dict:
    """Health check público."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "uptime_ms": int(time.process_time() * 1000),
    }


@app.get("/echo", tags=["utils"])
async def echo_get(request: Request) -> dict:
    """Refleja headers, query params y metadata del request."""
    return {
        "method": "GET",
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "url": str(request.url),
        "client": request.client.host if request.client else None,
    }


@app.post("/echo", tags=["utils"])
async def echo_post(request: Request) -> dict:
    """Refleja el body y headers del request."""
    try:
        body = await request.json()
    except Exception:
        body = (await request.body()).decode(errors="replace")
    return {
        "method": "POST",
        "headers": dict(request.headers),
        "body": body,
        "query_params": dict(request.query_params),
    }


@app.get("/slow", tags=["utils"])
async def slow_response(ms: int = Query(500, ge=0, le=10000)) -> dict:
    """Respuesta lenta. Útil para probar timeouts."""
    await asyncio.sleep(ms / 1000)
    return {"slept_ms": ms, "message": "respuesta lenta OK"}


@app.get("/error/{code}", tags=["utils"])
async def force_error(code: int = Path(..., ge=400, le=599)) -> JSONResponse:
    """Fuerza un código de error HTTP específico."""
    messages = {
        400: "Bad Request — parámetros inválidos",
        401: "Unauthorized — autenticación requerida",
        403: "Forbidden — sin permisos",
        404: "Not Found — recurso no existe",
        409: "Conflict — el recurso ya existe",
        422: "Unprocessable Entity — error de validación",
        429: "Too Many Requests — rate limit alcanzado",
        500: "Internal Server Error — error del servidor",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }
    return JSONResponse(
        status_code=code,
        content={"error": messages.get(code, f"Error {code}"), "code": code},
    )


@app.get("/paginate", tags=["utils"])
async def paginate(
    page: int = Query(1, ge=1),
    limit: int = Query(5, ge=1, le=100),
    _auth: str = Depends(flexible_auth),
) -> PaginatedResponse:
    """Endpoint paginado de ejemplo."""
    items = [{"index": i, "value": f"item-{i}"} for i in range(1, 51)]
    start = (page - 1) * limit
    end = start + limit
    return PaginatedResponse(
        data=items[start:end],
        page=page,
        limit=limit,
        total=len(items),
        has_next=end < len(items),
    )


# ---------------------------------------------------------------------------
# Users — CRUD completo
# ---------------------------------------------------------------------------

@app.get("/users", tags=["users"])
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    role: str | None = Query(None),
    active: bool | None = Query(None),
    _auth: str = Depends(flexible_auth),
) -> PaginatedResponse:
    """Lista usuarios. Filtra por role y active."""
    users = list(_users.values())
    if role:
        users = [u for u in users if u["role"] == role]
    if active is not None:
        users = [u for u in users if u["active"] == active]
    start = (page - 1) * limit
    chunk = users[start : start + limit]
    return PaginatedResponse(data=chunk, page=page, limit=limit, total=len(users), has_next=start + limit < len(users))


@app.post("/users", status_code=201, tags=["users"])
async def create_user(
    payload: UserCreate,
    _auth: str = Depends(flexible_auth),
) -> dict:
    """Crea un usuario. Retorna 201 con el recurso creado."""
    global _next_user_id
    user = {
        "id": _next_user_id,
        "name": payload.name,
        "email": payload.email,
        "role": payload.role,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _users[_next_user_id] = user
    _next_user_id += 1
    return user


@app.get("/users/{user_id}", tags=["users"])
async def get_user(
    user_id: int,
    _auth: str = Depends(flexible_auth),
) -> dict:
    """Obtiene un usuario por ID."""
    user = _users.get(user_id)
    if not user:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")
    return user


@app.put("/users/{user_id}", tags=["users"])
async def replace_user(
    user_id: int,
    payload: UserCreate,
    _auth: str = Depends(flexible_auth),
) -> dict:
    """Reemplaza un usuario (PUT semántica completa)."""
    if user_id not in _users:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")
    user = {
        "id": user_id,
        "name": payload.name,
        "email": payload.email,
        "role": payload.role,
        "active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _users[user_id] = user
    return user


@app.patch("/users/{user_id}", tags=["users"])
async def update_user(
    user_id: int,
    payload: UserUpdate,
    _auth: str = Depends(flexible_auth),
) -> dict:
    """Actualiza campos de un usuario (PATCH semántica parcial)."""
    user = _users.get(user_id)
    if not user:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")
    updates = payload.model_dump(exclude_none=True)
    user.update(updates)
    user["updated_at"] = datetime.now(timezone.utc).isoformat()
    return user


@app.delete("/users/{user_id}", status_code=204, tags=["users"])
async def delete_user(
    user_id: int,
    _auth: str = Depends(flexible_auth),
) -> None:
    """Elimina un usuario. Retorna 204 sin body."""
    if user_id not in _users:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")
    del _users[user_id]


# ---------------------------------------------------------------------------
# Posts — recurso anidado + standalone
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/posts", tags=["posts"])
async def get_user_posts(
    user_id: int,
    published: bool | None = Query(None),
    _auth: str = Depends(flexible_auth),
) -> list[dict]:
    """Posts de un usuario específico."""
    if user_id not in _users:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")
    posts = [p for p in _posts.values() if p["user_id"] == user_id]
    if published is not None:
        posts = [p for p in posts if p["published"] == published]
    return posts


@app.post("/users/{user_id}/posts", status_code=201, tags=["posts"])
async def create_user_post(
    user_id: int,
    payload: PostCreate,
    _auth: str = Depends(flexible_auth),
) -> dict:
    """Crea un post para un usuario."""
    global _next_post_id
    if user_id not in _users:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")
    post = {
        "id": _next_post_id,
        "user_id": user_id,
        "title": payload.title,
        "body": payload.body,
        "published": payload.published,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _posts[_next_post_id] = post
    _next_post_id += 1
    return post


@app.get("/posts", tags=["posts"])
async def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    published: bool | None = Query(None),
    _auth: str = Depends(flexible_auth),
) -> PaginatedResponse:
    """Lista todos los posts con paginación."""
    posts = list(_posts.values())
    if published is not None:
        posts = [p for p in posts if p["published"] == published]
    start = (page - 1) * limit
    chunk = posts[start : start + limit]
    return PaginatedResponse(data=chunk, page=page, limit=limit, total=len(posts), has_next=start + limit < len(posts))


@app.get("/posts/{post_id}", tags=["posts"])
async def get_post(
    post_id: int,
    _auth: str = Depends(flexible_auth),
) -> dict:
    post = _posts.get(post_id)
    if not post:
        raise HTTPException(404, f"Post {post_id} no encontrado")
    return post


@app.delete("/posts/{post_id}", status_code=204, tags=["posts"])
async def delete_post(
    post_id: int,
    _auth: str = Depends(flexible_auth),
) -> None:
    if post_id not in _posts:
        raise HTTPException(404, f"Post {post_id} no encontrado")
    del _posts[post_id]


# ---------------------------------------------------------------------------
# Auth especiales
# ---------------------------------------------------------------------------

@app.get("/protected/basic", tags=["auth"])
async def protected_basic(
    credentials: HTTPBasicCredentials | None = Depends(basic_scheme),
) -> dict:
    """Requiere Basic Auth: admin / secret."""
    if not credentials:
        raise HTTPException(401, "Basic Auth requerido", headers={"WWW-Authenticate": "Basic"})
    valid = secrets.compare_digest(credentials.username, "admin") and \
            secrets.compare_digest(credentials.password, "secret")
    if not valid:
        raise HTTPException(401, "Credenciales básicas inválidas", headers={"WWW-Authenticate": "Basic"})
    return {"authenticated": True, "user": credentials.username, "method": "basic"}


@app.get("/protected/apikey", tags=["auth"])
async def protected_apikey(
    _auth: str = Depends(require_api_key),
) -> dict:
    """Requiere header X-Api-Key: testkey-12345."""
    return {"authenticated": True, "method": "apikey"}


@app.get("/protected/bearer", tags=["auth"])
async def protected_bearer(
    _auth: str = Depends(require_bearer),
) -> dict:
    """Requiere Bearer token obtenido de /auth/token."""
    return {"authenticated": True, "method": "bearer", "token_prefix": _auth[:12] + "..."}


# ---------------------------------------------------------------------------
# Middleware: X-Request-Id y X-Response-Time
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.monotonic()
    request_id = str(uuid.uuid4())[:8]
    response = await call_next(request)
    ms = int((time.monotonic() - start) * 1000)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Response-Time-Ms"] = str(ms)
    return response


# ---------------------------------------------------------------------------
# Entrypoint directo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("testapi.main:app", host="0.0.0.0", port=8000, reload=True)
