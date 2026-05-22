"""
Tests de AssertionEngine
"""
from __future__ import annotations

import pytest

from xaip.core.assertions import AssertionEngine


@pytest.fixture
def engine():
    return AssertionEngine()


def test_status_equals_passes(engine):
    r = engine.evaluate("status=200", 200, {}, {}, 50)
    assert r.passed


def test_status_equals_fails(engine):
    r = engine.evaluate("status=200", 404, {}, {}, 50)
    assert not r.passed


def test_status_gte(engine):
    r = engine.evaluate("status>=200", 200, {}, {}, 50)
    assert r.passed
    r2 = engine.evaluate("status>=200", 199, {}, {}, 50)
    assert not r2.passed


def test_status_lt(engine):
    r = engine.evaluate("status<400", 201, {}, {}, 50)
    assert r.passed


def test_body_field_equals(engine):
    r = engine.evaluate("body.id=42", 200, {}, {"id": 42}, 10)
    assert r.passed


def test_body_nested(engine):
    r = engine.evaluate("body.user.age>=18", 200, {}, {"user": {"age": 25}}, 10)
    assert r.passed


def test_body_exists(engine):
    r = engine.evaluate("body.token exists", 200, {}, {"token": "abc"}, 10)
    assert r.passed


def test_body_not_exists(engine):
    r = engine.evaluate("body.secret exists", 200, {}, {}, 10)
    assert not r.passed


def test_header_equals(engine):
    r = engine.evaluate("headers.Content-Type=application/json", 200,
                        {"content-type": "application/json"}, {}, 10)
    assert r.passed


def test_ms_lte(engine):
    r = engine.evaluate("ms<=500", 200, {}, {}, 100)
    assert r.passed
    r2 = engine.evaluate("ms<=50", 200, {}, {}, 200)
    assert not r2.passed
