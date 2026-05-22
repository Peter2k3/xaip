"""
Tests de CollectionRunner (mock httpx)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from xaip.core.models import (
    Collection,
    CollectionStep,
    Environment,
    HttpMethod,
    NoAuth,
    StepRequest,
    StepStatus,
)
from xaip.core.runner import CollectionRunner


def make_env(base_url: str = "http://mock") -> Environment:
    return Environment(name="test", baseUrl=base_url, auth=NoAuth())


def make_step(
    step_id: str,
    method: str = "GET",
    path: str = "/test",
    expect: list[str] | None = None,
    depends_on: list[str] | None = None,
    always: bool = False,
) -> CollectionStep:
    return CollectionStep(
        id=step_id,
        name=step_id,
        dependsOn=depends_on or [],
        always=always,
        request=StepRequest(method=HttpMethod(method), path=path),
        expect=expect or [],
    )


def mock_response(status: int = 200, body: dict | None = None) -> AsyncMock:
    from xaip.http.client import ResponseData
    resp = ResponseData(
        status=status,
        headers={"content-type": "application/json"},
        body=body or {},
        duration_ms=10,
    )
    return resp


@pytest.mark.asyncio
async def test_single_step_passes():
    col = Collection(id="c1", name="c1", steps=[make_step("s1", expect=["status=200"])])
    env = make_env()

    with patch("xaip.core.runner.HttpClient") as MockClient:
        instance = MockClient.return_value
        instance.request = AsyncMock(return_value=mock_response(200))
        runner = CollectionRunner(env)
        result = await runner.run(col)

    assert result.exit_code == 0
    assert result.steps[0].status == StepStatus.PASSED


@pytest.mark.asyncio
async def test_single_step_fails_assertion():
    col = Collection(id="c1", name="c1", steps=[make_step("s1", expect=["status=201"])])
    env = make_env()

    with patch("xaip.core.runner.HttpClient") as MockClient:
        instance = MockClient.return_value
        instance.request = AsyncMock(return_value=mock_response(200))
        runner = CollectionRunner(env)
        result = await runner.run(col)

    assert result.exit_code != 0
    assert result.steps[0].status == StepStatus.FAILED


@pytest.mark.asyncio
async def test_stop_on_failure():
    steps = [
        make_step("s1", expect=["status=201"]),  # fallará
        make_step("s2"),
    ]
    col = Collection(id="c1", name="c1", steps=steps)
    env = make_env()

    with patch("xaip.core.runner.HttpClient") as MockClient:
        instance = MockClient.return_value
        instance.request = AsyncMock(return_value=mock_response(200))
        runner = CollectionRunner(env)
        result = await runner.run(col, stop_on_failure=True)

    statuses = [s.status for s in result.steps]
    assert StepStatus.SKIPPED in statuses


@pytest.mark.asyncio
async def test_only_filter():
    steps = [make_step("s1"), make_step("s2"), make_step("s3")]
    col = Collection(id="c1", name="c1", steps=steps)
    env = make_env()

    with patch("xaip.core.runner.HttpClient") as MockClient:
        instance = MockClient.return_value
        instance.request = AsyncMock(return_value=mock_response(200))
        runner = CollectionRunner(env)
        result = await runner.run(col, only=["s2"])

    executed = [s.id for s in result.steps if s.status != StepStatus.SKIPPED]
    assert executed == ["s2"]
