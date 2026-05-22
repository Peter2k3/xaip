"""
Tests de VariableResolver
"""
from __future__ import annotations

import pytest

from xaip.core.resolver import VariableResolver


@pytest.fixture
def resolver():
    return VariableResolver(
        env_vars={"BASE": "https://api.example.com", "TOKEN": "secret123"},
        session_vars={"sessionKey": "sess_abc"},
    )


def test_no_template(resolver):
    assert resolver.resolve("hello") == "hello"


def test_env_var(resolver):
    assert resolver.resolve("{{env.BASE}}") == "https://api.example.com"


def test_session_var(resolver):
    assert resolver.resolve("{{session.sessionKey}}") == "sess_abc"


def test_composite_string(resolver):
    result = resolver.resolve("{{env.BASE}}/users/{{session.sessionKey}}")
    assert result == "https://api.example.com/users/sess_abc"


def test_dict_recursion(resolver):
    d = {"url": "{{env.BASE}}", "nested": {"token": "{{env.TOKEN}}"}}
    result = resolver.resolve(d)
    assert result == {"url": "https://api.example.com", "nested": {"token": "secret123"}}


def test_list_recursion(resolver):
    lst = ["{{env.BASE}}", "static"]
    result = resolver.resolve(lst)
    assert result == ["https://api.example.com", "static"]


def test_unknown_var(resolver):
    # Variables no definidas se dejan sin resolver
    result = resolver.resolve("{{env.MISSING}}")
    assert result == "{{env.MISSING}}"


def test_step_var(resolver):
    # Simula lo que almacena el runner: saved vars + body
    resolver.set_step("login", {"token": "tok123", "body": {"user": {"id": 1}}})
    assert resolver.resolve("{{login.token}}") == "tok123"
    assert resolver.resolve("{{login.body.user.id}}") == 1


def test_step_var_simple(resolver):
    resolver.set_step("step1", {"id": 42})
    assert resolver.resolve("{{step1.id}}") == 42
