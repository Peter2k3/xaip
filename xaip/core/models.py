"""
XAIP — AI-Driven API Tester
Core data models (Pydantic v2)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------

class AuthType(str, Enum):
    BEARER = "bearer"
    API_KEY = "apikey"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    OAUTH2_ROPC = "oauth2-ropc"
    NONE = "none"


class ApiKeyLocation(str, Enum):
    HEADER = "header"
    QUERY = "query"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------

class BearerAuth(BaseModel):
    type: AuthType = AuthType.BEARER
    token: str | None = None
    token_cmd: str | None = Field(None, alias="tokenCmd")
    token_from_var: str | None = Field(None, alias="tokenFromVar")

    model_config = {"populate_by_name": True}


class ApiKeyAuth(BaseModel):
    type: AuthType = AuthType.API_KEY
    location: ApiKeyLocation = ApiKeyLocation.HEADER
    name: str  # header name or query param name
    value: str | None = None
    value_cmd: str | None = Field(None, alias="valueCmd")

    model_config = {"populate_by_name": True}


class BasicAuth(BaseModel):
    type: AuthType = AuthType.BASIC
    user: str
    password: str | None = None
    password_cmd: str | None = Field(None, alias="passwordCmd")

    model_config = {"populate_by_name": True}


class OAuth2Auth(BaseModel):
    type: AuthType = AuthType.OAUTH2
    token_url: str = Field(alias="tokenUrl")
    client_id: str = Field(alias="clientId")
    client_secret: str | None = Field(None, alias="clientSecret")
    client_secret_cmd: str | None = Field(None, alias="clientSecretCmd")
    scope: str | None = None
    # Runtime only — not persisted
    cached_token: str | None = Field(None, exclude=True)
    token_expires_at: float | None = Field(None, exclude=True)

    model_config = {"populate_by_name": True}


class OAuth2RopcAuth(BaseModel):
    type: AuthType = AuthType.OAUTH2_ROPC
    token_url: str = Field(alias="tokenUrl")
    client_id: str = Field(alias="clientId")
    username: str
    password: str | None = None
    password_cmd: str | None = Field(None, alias="passwordCmd")
    scope: str | None = None
    cached_token: str | None = Field(None, exclude=True)
    token_expires_at: float | None = Field(None, exclude=True)

    model_config = {"populate_by_name": True}


class NoAuth(BaseModel):
    type: AuthType = AuthType.NONE


AuthConfig = BearerAuth | ApiKeyAuth | BasicAuth | OAuth2Auth | OAuth2RopcAuth | NoAuth


# ---------------------------------------------------------------------------
# Entornos
# ---------------------------------------------------------------------------

class Environment(BaseModel):
    name: str = ""
    base_url: str = Field(alias="baseUrl")
    auth: AuthConfig | None = None
    vars: dict[str, str] = {}

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def parse_auth(cls, data: Any) -> Any:
        if isinstance(data, dict) and "auth" in data and isinstance(data["auth"], dict):
            auth_map: dict[str, type] = {
                AuthType.BEARER: BearerAuth,
                AuthType.API_KEY: ApiKeyAuth,
                AuthType.BASIC: BasicAuth,
                AuthType.OAUTH2: OAuth2Auth,
                AuthType.OAUTH2_ROPC: OAuth2RopcAuth,
                AuthType.NONE: NoAuth,
            }
            t = data["auth"].get("type", AuthType.NONE)
            klass = auth_map.get(t, NoAuth)
            data["auth"] = klass(**data["auth"])
        return data


# ---------------------------------------------------------------------------
# Endpoints escaneados
# ---------------------------------------------------------------------------

class ParamSchema(BaseModel):
    name: str
    location: str  # "path" | "query" | "header" | "body"
    type: str = "string"
    required: bool = False
    description: str | None = None


class EndpointSchema(BaseModel):
    id: str  # ej: "catalogo.crearCuenta"
    controller: str | None = None
    method: HttpMethod
    path: str
    tags: list[str] = []
    params: list[ParamSchema] = []
    body_schema: dict[str, Any] | None = Field(None, alias="bodySchema")
    response_schema: dict[str, Any] | None = Field(None, alias="responseSchema")
    description: str | None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Colecciones
# ---------------------------------------------------------------------------

class StepRequest(BaseModel):
    method: HttpMethod
    path: str
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    body: Any = None
    body_file: str | None = Field(None, alias="bodyFile")
    form: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class AssertionExpr(BaseModel):
    """Una aserción cruda, ej: 'status=200' o 'body.activa=true'"""
    expr: str


class CollectionStep(BaseModel):
    id: str
    name: str | None = None
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    parallel: bool = False
    run_if: str | None = Field(None, alias="runIf")
    always: bool = False
    retry: int = 0
    retry_delay: str | None = Field(None, alias="retryDelay")  # "2s", "500ms"
    retry_until: str | None = Field(None, alias="retryUntil")
    timeout: str | None = None  # "30s"
    request: StepRequest
    expect: list[str] = []
    save: dict[str, str] = {}  # varName -> jsonpath expression
    as_auth: bool = Field(False, alias="asAuth")

    model_config = {"populate_by_name": True}


class Collection(BaseModel):
    id: str
    name: str
    steps: list[CollectionStep] = []


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------

class AssertionResult(BaseModel):
    expr: str
    passed: bool
    actual: Any = None
    message: str | None = None


class StepResult(BaseModel):
    id: str
    name: str | None = None
    status: StepStatus
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    assertions: list[AssertionResult] = []
    saved: dict[str, Any] = {}
    error: str | None = None
    duration_ms: int = 0


class RunResult(BaseModel):
    id: str
    collection: str | None = None
    endpoint: str | None = None
    env: str
    started_at: datetime = Field(alias="startedAt", default_factory=datetime.utcnow)
    duration_ms: int = Field(0, alias="duration")
    steps: list[StepResult] = []
    summary: dict[str, int] = {}
    exit_code: int = Field(0, alias="exitCode")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Raíz: .xaip.json
# ---------------------------------------------------------------------------

class XaipConfig(BaseModel):
    project: str = "xaip-project"
    version: str = "1"
    scanned_at: str | None = Field(None, alias="scannedAt")
    active_env: str = Field("dev", alias="activeEnv")
    environments: dict[str, Environment] = {}
    endpoints: list[EndpointSchema] = []
    collections: list[Collection] = []
    history: list[RunResult] = []

    model_config = {"populate_by_name": True}

    def get_active_env(self) -> Environment | None:
        return self.environments.get(self.active_env)

    def get_collection(self, name: str) -> Collection | None:
        return next((c for c in self.collections if c.id == name), None)

    def get_endpoint(self, id_or_path: str) -> EndpointSchema | None:
        return next(
            (e for e in self.endpoints if e.id == id_or_path or e.path == id_or_path),
            None,
        )
