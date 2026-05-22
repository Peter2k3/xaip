"""
Importadores para Postman y curl parsing.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from xaip.core.models import Collection, CollectionStep, HttpMethod, StepRequest


# ---------------------------------------------------------------------------
# Postman Collection v2.1
# ---------------------------------------------------------------------------

def import_postman_collection(data: dict) -> Collection:
    """Convierte una Postman Collection v2.x en una Collection XAIP."""
    name = data.get("info", {}).get("name", "postman-import")
    col_id = name.lower().replace(" ", "-")
    steps: list[CollectionStep] = []

    for item in _flatten_postman_items(data.get("item", [])):
        req_data = item.get("request", {})
        if not req_data:
            continue

        method = str(req_data.get("method", "GET")).upper()
        url_obj = req_data.get("url", {})
        if isinstance(url_obj, str):
            path = "/" + url_obj.split("/", 3)[-1] if "/" in url_obj else url_obj
        else:
            raw_path = "/".join(url_obj.get("path", []))
            path = f"/{raw_path}"

        headers: dict[str, str] = {}
        for h in req_data.get("header", []):
            if not h.get("disabled"):
                headers[h.get("key", "")] = h.get("value", "")

        body: Any = None
        body_obj = req_data.get("body", {}) or {}
        mode = body_obj.get("mode")
        if mode == "raw":
            raw = body_obj.get("raw", "")
            try:
                import json
                body = json.loads(raw)
            except Exception:
                body = raw
        elif mode == "urlencoded":
            body = {x["key"]: x.get("value", "") for x in body_obj.get("urlencoded", [])}

        step_id = item.get("name", str(uuid.uuid4())[:8]).lower().replace(" ", "-")
        steps.append(
            CollectionStep(
                id=step_id,
                name=item.get("name", step_id),
                request=StepRequest(
                    method=HttpMethod(method),
                    path=path,
                    headers=headers,
                    body=body,
                ),
            )
        )

    return Collection(id=col_id, name=name, steps=steps)


def _flatten_postman_items(items: list[dict]) -> list[dict]:
    """Aplana carpetas de Postman recursivamente."""
    result = []
    for item in items:
        if "item" in item:
            result.extend(_flatten_postman_items(item["item"]))
        else:
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# curl parser
# ---------------------------------------------------------------------------

def parse_curl_command(curl_str: str) -> CollectionStep:
    """Parsea un comando curl y devuelve un CollectionStep."""
    # Normalizar saltos de línea
    curl_str = curl_str.replace("\\\n", " ").strip()
    if curl_str.startswith("curl "):
        curl_str = curl_str[5:].strip()

    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body: Any = None

    # URL (primer token que parece URL o el que sigue a -X)
    tokens = _tokenize_curl(curl_str)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()
        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                raw = tokens[i]
                if ": " in raw:
                    k, v = raw.split(": ", 1)
                elif ":" in raw:
                    k, v = raw.split(":", 1)
                else:
                    k, v = raw, ""
                headers[k.strip()] = v.strip()
        elif tok in ("-d", "--data", "--data-raw", "--data-binary"):
            i += 1
            if i < len(tokens):
                raw_body = tokens[i]
                try:
                    import json
                    body = json.loads(raw_body)
                    if not method or method == "GET":
                        method = "POST"
                except Exception:
                    body = raw_body
        elif tok.startswith("http://") or tok.startswith("https://"):
            url = tok
        elif not tok.startswith("-") and not url:
            url = tok
        i += 1

    # Extraer path de la URL
    if url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
    else:
        path = "/"

    step_id = str(uuid.uuid4())[:8]
    return CollectionStep(
        id=step_id,
        name=f"{method} {path}",
        request=StepRequest(
            method=HttpMethod(method or "GET"),
            path=path,
            headers=headers,
            body=body,
        ),
    )


def _tokenize_curl(s: str) -> list[str]:
    """Tokeniza una línea de curl respetando comillas."""
    tokens: list[str] = []
    current = []
    in_quote: str | None = None
    i = 0
    while i < len(s):
        c = s[i]
        if c in ('"', "'") and in_quote is None:
            in_quote = c
        elif c == in_quote:
            in_quote = None
        elif c == " " and in_quote is None:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(c)
        i += 1
    if current:
        tokens.append("".join(current))
    return tokens
