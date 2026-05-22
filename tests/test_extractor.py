"""
Tests de ValueExtractor
"""
from __future__ import annotations

import pytest

from xaip.core.extractor import ValueExtractor


@pytest.fixture
def ex():
    return ValueExtractor()


def test_status(ex):
    assert ex.extract("status", {}, {}, 201) == 201


def test_body_simple(ex):
    assert ex.extract("body.id", {"id": 99}, {}, 200) == 99


def test_body_nested(ex):
    body = {"user": {"email": "a@b.com"}}
    assert ex.extract("body.user.email", body, {}, 200) == "a@b.com"


def test_header(ex):
    headers = {"x-request-id": "abc-123"}
    assert ex.extract("headers.x-request-id", {}, headers, 200) == "abc-123"


def test_jsonpath(ex):
    body = {"items": [{"id": 1}, {"id": 2}]}
    val = ex.extract("$.items[0].id", body, {}, 200)
    assert val == 1


def test_missing_returns_none(ex):
    assert ex.extract("body.missing", {}, {}, 200) is None
