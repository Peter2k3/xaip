"""
Tests de importadores (Postman + curl)
"""
from __future__ import annotations

from xaip.utils.importers import import_postman_collection, parse_curl_command


POSTMAN_COLLECTION = {
    "info": {"name": "My API"},
    "item": [
        {
            "name": "Get Users",
            "request": {
                "method": "GET",
                "url": {"path": ["api", "users"]},
                "header": [{"key": "Accept", "value": "application/json"}],
            },
        },
        {
            "name": "Create User",
            "request": {
                "method": "POST",
                "url": {"path": ["api", "users"]},
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "body": {
                    "mode": "raw",
                    "raw": '{"name": "Alice"}',
                },
            },
        },
    ],
}


def test_postman_import_name():
    col = import_postman_collection(POSTMAN_COLLECTION)
    assert col.name == "My API"


def test_postman_import_steps():
    col = import_postman_collection(POSTMAN_COLLECTION)
    assert len(col.steps) == 2


def test_postman_import_body():
    col = import_postman_collection(POSTMAN_COLLECTION)
    create_step = col.steps[1]
    assert create_step.request.body == {"name": "Alice"}


def test_parse_curl_get():
    step = parse_curl_command("curl https://api.example.com/users")
    assert step.request.method.value == "GET"
    assert "/users" in step.request.path


def test_parse_curl_post_with_data():
    cmd = """curl -X POST https://api.example.com/users -H "Content-Type: application/json" -d '{"name":"Bob"}'"""
    step = parse_curl_command(cmd)
    assert step.request.method.value == "POST"
    assert step.request.body == {"name": "Bob"}
    assert step.request.headers.get("Content-Type") == "application/json"


def test_parse_curl_headers():
    cmd = "curl -H 'Authorization: Bearer tok' https://api.example.com/me"
    step = parse_curl_command(cmd)
    assert step.request.headers.get("Authorization") == "Bearer tok"
