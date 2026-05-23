# XAIP — AI-Driven API Tester

> CLI/TUI profesional para testear APIs REST con autenticación avanzada, colecciones encadenadas, aserciones y exportación automatizada.

```
xaip run GET /users --expect "status=200" --expect "body.total>=1"
```
    
---

## Tabla de contenidos

1. [Instalación](#instalación)
2. [Inicio rápido](#inicio-rápido)
3. [Arquitectura](#arquitectura)
4. [Configuración (.xaip.json)](#configuración-xaipjson)
5. [Entornos](#entornos)
6. [Autenticación](#autenticación)
7. [Comandos](#comandos)
8. [Colecciones y pasos](#colecciones-y-pasos)
9. [Variables y plantillas](#variables-y-plantillas)
10. [Aserciones](#aserciones)
11. [Historial y Diff](#historial-y-diff)
12. [Importar / Exportar](#importar--exportar)
13. [TUI interactiva](#tui-interactiva)
14. [API de prueba local](#api-de-prueba-local)
15. [Desarrollo y tests](#desarrollo-y-tests)

---

## Instalación

**Requisitos:** Python 3.11+

```bash
# Desde el repositorio
git clone https://github.com/tuorg/xaip
cd xaip
pip install -e ".[dev]"
```

**Dependencias principales:**

| Paquete | Uso |
|---|---|
| `typer ≥ 0.12` | CLI framework |
| `pydantic v2` | Modelos de datos |
| `httpx[http2] ≥ 0.27` | Cliente HTTP async |
| `authlib ≥ 1.3` | Flujos OAuth2 |
| `textual ≥ 0.60` | TUI interactiva |
| `rich ≥ 13` | Output en terminal |
| `deepdiff ≥ 7` | Diff entre runs |
| `jsonpath-ng ≥ 1.6` | Expresiones JSONPath |
| `javalang ≥ 0.13` | Scanner Spring Boot |

---

## Inicio rápido

```bash
# 1. Inicializar workspace en el directorio del proyecto
xaip init

# 2. Escanear endpoints (detecta Spring Boot, FastAPI u OpenAPI)
xaip scan

# 3. Ejecutar un request ad-hoc
xaip run GET /health
xaip run POST /users --body '{"name":"Alice","email":"a@b.com"}' --expect "status=201"

# 4. Ejecutar una colección completa
xaip collection run crud-users --env local

# 5. Abrir la TUI
xaip tui
```

---

## Arquitectura

```
xaip/
├── core/
│   ├── models.py        # Pydantic v2 — fuente única de verdad de tipos
│   ├── config_repo.py   # Repository pattern — lee/escribe .xaip.json
│   ├── resolver.py      # Template variables {{env.X}}, {{session.X}}, {{stepId.X}}
│   ├── assertions.py    # Chain of Responsibility — evalúa expresiones
│   ├── extractor.py     # JSONPath + dot-path extraction
│   └── runner.py        # DAG execution — dependencias, retries, teardown
├── auth/
│   └── providers.py     # Strategy pattern — Bearer, Basic, ApiKey, OAuth2
├── http/
│   └── client.py        # Facade sobre httpx.AsyncClient
├── scanners/
│   ├── base.py          # Template Method — BaseScanner
│   ├── spring_boot.py   # javalang AST + regex fallback
│   ├── fastapi.py       # ast stdlib
│   └── openapi.py       # OpenAPI 3.x (file/URL)
├── commands/            # Un typer.Typer() por grupo de comandos
├── tui/app.py           # Textual TUI
└── main.py              # Entry point — registra todos los comandos
```

**Patrones de diseño aplicados:**

| Patrón | Dónde |
|---|---|
| Repository | `ConfigRepository` |
| Strategy | `AuthProvider` (bearer, basic, apikey, oauth2) |
| Template Method | `BaseScanner` |
| Facade | `HttpClient`, utilidades CLI |
| Chain of Responsibility | `AssertionEngine` |
| Command | pasos del `CollectionRunner` |
| Registry + CoR | detección de stack en `scanners/__init__.py` |
| Factory | `build_provider(auth_config)` |

---

## Configuración (.xaip.json)

XAIP busca `.xaip.json` desde el directorio actual hacia arriba (igual que `git`).

```jsonc
{
  "project": "mi-api",
  "version": "1",
  "activeEnv": "dev",
  "environments": { ... },
  "endpoints": [ ... ],       // poblados por `xaip scan`
  "collections": [ ... ],     // definidos manualmente o importados
  "history": [ ... ]          // llenado automáticamente por cada run
}
```

---

## Entornos

```bash
# Crear entorno
xaip env create staging --base-url https://staging.api.com

# Listar
xaip env list

# Activar
xaip env set staging

# Variables de entorno
xaip env var set API_VERSION v2 --env staging
xaip env var get API_VERSION

# Cambiar entorno por comando (no persiste)
xaip run GET /users --env staging
```

---

## Autenticación

### Bearer Token (estático)
```bash
xaip auth set bearer --token "eyJhbGc..."
```

### Bearer Token (desde comando)
```bash
xaip auth set bearer --token-cmd "vault kv get -field=token secret/api"
```

### API Key
```bash
# En header
xaip auth set apikey --header X-Api-Key --value "mykey-123"
# En query param
xaip auth set apikey --query api_key --value "mykey-123"
```

### Basic Auth
```bash
xaip auth set basic --user admin --password secret
# O desde variable de entorno segura
xaip auth set basic --user admin --password-cmd "echo $API_PASS"
```

### OAuth2 Client Credentials
```bash
xaip auth set oauth2 \
  --token-url https://auth.example.com/oauth/token \
  --client-id my-app \
  --client-secret "$(cat .client-secret)" \
  --scope "read write"
```

### OAuth2 ROPC (Resource Owner Password)
```bash
xaip auth set oauth2-ropc \
  --token-url https://auth.example.com/token \
  --client-id my-app \
  --username admin \
  --password secret
```

### Probar auth
```bash
xaip auth test
xaip auth test --endpoint "GET /me"  # con probe request
xaip auth refresh                     # fuerza renovación de token
```

---

## Comandos

### `xaip init`
Inicializa el workspace. Detecta stack automáticamente, pregunta base URL y crea `.xaip.json`.

```bash
xaip init
xaip init --spec https://api.example.com/openapi.json  # importar spec OpenAPI
```

### `xaip scan`
Escanea el proyecto y actualiza los endpoints en `.xaip.json`.

```bash
xaip scan                      # auto-detecta stack
xaip scan --stack spring-boot  # forzar scanner
```

### `xaip run`
Request ad-hoc.

```bash
xaip run GET /users
xaip run GET /users --param page=2 --param limit=5
xaip run POST /users \
  --body '{"name":"Alice","email":"a@b.com"}' \
  --expect "status=201" \
  --expect "body.id exists" \
  --save "userId=body.id"

xaip run PUT /users/42 \
  --header "X-Trace-Id: abc123" \
  --body-file payload.json \
  --env production

xaip run GET /report --dry-run      # muestra request sin enviar
xaip run GET /slow --timeout 5s

# Omitir auth config del entorno (útil para endpoints públicos)
xaip run GET /health --no-auth

# Auth explícita sin entorno (--no-auth evita que el provider
# del entorno interfiera con el header manual)
xaip run GET /api/users --no-auth -H "Authorization: Bearer $TOKEN"

# Output modes
xaip run GET /users --output table       # status + aserciones
xaip run GET /users --output body-only   # solo el body de la respuesta
xaip run GET /users --output json        # completo (default)
```

### `xaip endpoints`
```bash
xaip endpoints list
xaip endpoints list --method GET --path "/users*"
xaip endpoints show getUserById
xaip endpoints curl getUserById    # genera curl command
```

### `xaip env`
```bash
xaip env list
xaip env show dev
xaip env create prod --base-url https://api.example.com
xaip env delete staging
xaip env set prod              # activa entorno
xaip env var set KEY valor
xaip env var get KEY
xaip env var list
xaip env var delete KEY
```

### `xaip auth`
Ver sección [Autenticación](#autenticación).

### `xaip collection`
Ver sección [Colecciones y pasos](#colecciones-y-pasos).

### `xaip history`
```bash
xaip history list
xaip history list --collection crud-users --status failed
xaip history show last
xaip history show abc12345
xaip history clear --older-than 30d
xaip history clear --all
```

### `xaip diff`
```bash
xaip diff                          # compara los dos últimos runs
xaip diff abc12345 def67890
xaip diff --collection crud-users  # filtra por colección
xaip diff --baseline abc12345      # compara baseline vs último
```

### `xaip import`
```bash
xaip import openapi ./swagger.yaml
xaip import openapi https://petstore3.swagger.io/api/v3/openapi.json
xaip import postman ./My_Collection.postman_collection.json
xaip import curl 'curl -X POST https://api.com/users -H "Content-Type: application/json" -d '"'"'{"name":"Bob"}'"'"''
```

### `xaip export`
```bash
xaip export pytest --collection crud-users --output tests/test_api.py
xaip export curl --collection smoke
xaip export markdown --collection crud-users --output docs/api-tests.md
```

### `xaip session`
Variables efímeras para la sesión actual del CLI.

```bash
xaip session set token "Bearer xyz"
xaip session get token
xaip session list
xaip session clear
```

### `xaip var resolve`
```bash
xaip var resolve "{{env.BASE_URL}}/users/{{session.userId}}"
```

### Utilidades
```bash
xaip doctor           # diagnóstico del entorno
xaip validate         # valida .xaip.json contra el schema
xaip fixture getUser  # genera payload de ejemplo para un endpoint
xaip edit             # abre .xaip.json en $EDITOR
xaip version
```

---

## Colecciones y pasos

Una colección es una secuencia (o DAG) de pasos HTTP que comparten variables.

### Gestión
```bash
xaip collection list
xaip collection create auth-flow
xaip collection copy auth-flow auth-flow-v2
xaip collection rename auth-flow login-flow
xaip collection delete auth-flow

# Pasos
xaip collection step add crud-users POST /users \
  --name "Crear usuario" \
  --body '{"name":"Test"}' \
  --expect "status=201" \
  --save "userId=body.id"

xaip collection step add crud-users GET /users/{{session.userId}} \
  --name "Leer usuario" \
  --depends-on create-user \
  --expect "status=200"

xaip collection step list crud-users
xaip collection step remove crud-users step-id
xaip collection step move crud-users step-id --after other-step
xaip collection step edit crud-users step-id --name "Nuevo nombre"
```

### Ejecución
```bash
xaip collection run crud-users
xaip collection run crud-users --env staging
xaip collection run crud-users --only "create-user,get-user"
xaip collection run crud-users --skip teardown
xaip collection run crud-users --stop-on-failure    # default
xaip collection run crud-users --continue-on-failure
xaip collection run crud-users --dry-run
xaip collection run crud-users --vars "prefix=test,suffix=001"
xaip collection run crud-users --output table
```

### Schema de un paso

```jsonc
{
  "id": "create-user",
  "name": "Crear usuario",
  "dependsOn": ["get-token"],     // DAG — espera que estos pasos terminen
  "parallel": false,               // ejecutar en paralelo con sus hermanos
  "runIf": "get-token.status=200", // condición para ejecutar
  "always": false,                 // true = se ejecuta aunque haya fallos (teardown)
  "retry": 3,                      // reintentos en caso de fallo
  "retryDelay": "2s",              // espera entre reintentos
  "retryUntil": "body.status=ready", // condición de éxito
  "timeout": "30s",
  "request": {
    "method": "POST",
    "path": "/users",
    "headers": { "X-Trace": "{{session.traceId}}" },
    "params": {},
    "body": { "name": "Alice" }
  },
  "expect": [
    "status=201",
    "body.id exists",
    "body.name=Alice",
    "ms<=500"
  ],
  "save": {
    "userId": "body.id",
    "userEmail": "body.email"
  },
  "asAuth": false   // true = el token guardado se usa para el resto de pasos
}
```

---

## Variables y plantillas

XAIP resuelve `{{namespace.key}}` en cualquier campo de texto de un paso.

| Expresión | Origen |
|---|---|
| `{{env.KEY}}` | Variables del entorno activo |
| `{{session.KEY}}` | Variables de sesión / guardadas por `--save` |
| `{{stepId.body.field}}` | Campo de la respuesta de un paso previo |
| `{{stepId.status}}` | Código HTTP de un paso previo |
| `{{stepId.headers.X-Id}}` | Header de un paso previo |

**Ejemplo de encadenamiento:**

```jsonc
// Paso 1 guarda el ID
{ "save": { "userId": "body.id" } }

// Paso 2 usa el ID en la URL
{ "path": "/users/{{session.userId}}/posts" }
```

---

## Aserciones

Las aserciones se evalúan con la sintaxis `campo operador valor`.

**Campos:**

| Campo | Descripción |
|---|---|
| `status` | Código HTTP de respuesta |
| `body.field.nested` | Valor en el JSON del body (dot-path) |
| `headers.Content-Type` | Valor de un header (case-insensitive) |
| `ms` | Duración de la petición en milisegundos |

**Operadores:**

| Op | Significado |
|---|---|
| `=` | Igualdad (coerce de tipo automático) |
| `!=` | Distinto |
| `>=` `<=` `>` `<` | Comparación numérica |
| `~=` | Contiene (regex o substring) |
| `exists` | El campo existe y no es null |

**Ejemplos:**

```bash
# En xaip run
--expect "status=200"
--expect "status>=200"
--expect "status<400"
--expect "body.total>=1"
--expect "body.user.active=true"
--expect "body.token exists"
--expect "headers.Content-Type~=application/json"
--expect "ms<=500"
```

---

## Historial y Diff

Cada ejecución de colección se guarda automáticamente en el array `history` de `.xaip.json`.

```bash
# Ver últimas ejecuciones
xaip history list --limit 10

# Comparar dos runs
xaip diff abc12345 def67890

# Comparar con baseline
xaip diff --baseline abc12345

# Comparar los dos últimos de una colección
xaip diff --collection crud-users
```

El diff usa `deepdiff` para detectar cambios en bodies de respuesta, tiempos, y códigos de estado entre runs.

---

## Importar / Exportar

### Importar OpenAPI
```bash
xaip import openapi ./openapi.yaml
xaip import openapi https://api.example.com/openapi.json
```

### Importar colección Postman
```bash
xaip import postman ./My_API.postman_collection.json
```

### Importar desde curl
```bash
xaip import curl 'curl -X POST https://api.com/login \
  -H "Content-Type: application/json" \
  -d '"'"'{"user":"admin","pass":"secret"}'"'"''
```

### Exportar tests pytest
```bash
xaip export pytest --collection crud-users --output tests/test_crud.py
```
Genera un archivo `pytest` real con `httpx` como cliente, listo para CI/CD.

### Exportar curl
```bash
xaip export curl --collection smoke
```

### Exportar documentación Markdown
```bash
xaip export markdown --collection crud-users --output docs/tests.md
```

---

## TUI interactiva

```bash
xaip tui
xaip tui --collection crud-users
xaip tui --env staging
```

**Atajos:**

| Tecla | Acción |
|---|---|
| `r` | Ejecutar paso/colección seleccionado |
| `e` | Foco en Endpoints |
| `c` | Foco en Colecciones |
| `?` | Mostrar ayuda |
| `q` | Salir |

La TUI muestra:
- Árbol de navegación (endpoints por controlador, colecciones con pasos)
- Panel de detalle del ítem seleccionado
- Tab de historial de los últimos 20 runs
- Tab de variables del entorno activo
- Log de ejecución en tiempo real

---

## API de prueba local

El proyecto incluye una API FastAPI completa para probar todas las features en ambiente local.

### Iniciar el servidor
```bash
pip install fastapi "uvicorn[standard]"
uvicorn testapi.main:app --reload --port 8000
```

Documentación interactiva disponible en `http://localhost:8000/docs`.

### Endpoints disponibles

| Método | Path | Auth | Descripción |
|---|---|---|---|
| `GET` | `/health` | No | Health check |
| `GET` | `/echo` | No | Refleja headers y query params |
| `POST` | `/echo` | No | Refleja el body |
| `GET` | `/slow?ms=N` | No | Respuesta lenta configurable |
| `GET` | `/error/{code}` | No | Fuerza código de error |
| `POST` | `/auth/token` | No | Obtiene Bearer token |
| `POST` | `/auth/oauth2/token` | No | OAuth2 (client_credentials / password) |
| `GET` | `/protected/bearer` | Bearer | Valida token |
| `GET` | `/protected/basic` | Basic | Valida `admin:secret` |
| `GET` | `/protected/apikey` | API Key | Valida `X-Api-Key: testkey-12345` |
| `GET` | `/users` | Bearer/Key | Lista usuarios (paginado) |
| `POST` | `/users` | Bearer/Key | Crea usuario |
| `GET` | `/users/{id}` | Bearer/Key | Obtiene usuario |
| `PUT` | `/users/{id}` | Bearer/Key | Reemplaza usuario |
| `PATCH` | `/users/{id}` | Bearer/Key | Actualización parcial |
| `DELETE` | `/users/{id}` | Bearer/Key | Elimina usuario |
| `GET` | `/users/{id}/posts` | Bearer/Key | Posts del usuario |
| `POST` | `/users/{id}/posts` | Bearer/Key | Crea post |
| `GET` | `/posts` | Bearer/Key | Lista posts (paginado) |
| `DELETE` | `/posts/{id}` | Bearer/Key | Elimina post |
| `GET` | `/paginate` | Bearer/Key | 50 ítems paginados |

**Credenciales de prueba:**

| Tipo | Valor |
|---|---|
| Bearer estático | `test-token-static-12345` |
| OAuth2 client | `xaip-client` / `xaip-secret` |
| Bearer dinámico | `POST /auth/token` con `admin:secret` |
| Basic Auth | `admin:secret` |
| API Key | `X-Api-Key: testkey-12345` |

### Ejecutar colecciones demo

Con el servidor corriendo:

```bash
# Inicializar con la config incluida
cd /path/to/xaip

# Smoke tests (sin auth especial)
xaip collection run smoke

# Auth flow con token dinámico
xaip collection run auth-flow

# CRUD completo con variables encadenadas
xaip collection run crud-users

# Demo de assertions avanzadas
xaip collection run assertions-demo

# Manejo de errores
xaip collection run error-scenarios --continue-on-failure

# Paginación y filtros
xaip collection run pagination-demo
```

---

## Desarrollo y tests

```bash
# Instalar con dependencias de desarrollo
pip install -e ".[dev]"

# Ejecutar tests
python -m pytest tests/ -v

# Tests específicos
python -m pytest tests/test_assertions.py -v
python -m pytest tests/test_runner.py -v
python -m pytest tests/test_importers.py -v

# Verificar entorno
xaip doctor

# Validar config
xaip validate
```

**Estructura de tests:**

| Archivo | Qué cubre |
|---|---|
| `tests/test_assertions.py` | AssertionEngine — todos los operadores y campos |
| `tests/test_resolver.py` | VariableResolver — env, session, step, nested paths |
| `tests/test_extractor.py` | ValueExtractor — dot-path, headers, JSONPath |
| `tests/test_runner.py` | CollectionRunner — single step, fallos, --only, stop-on-failure |
| `tests/test_importers.py` | Postman v2.x + curl parser |

---

## Licencia

MIT © 2026
