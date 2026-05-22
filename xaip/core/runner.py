"""
Motor de ejecución de colecciones.
Maneja dependencias (DAG), variables de sesión, aserciones, reintentos, teardown.
Pattern: Command + Chain of Responsibility
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, Callable

from xaip.auth.providers import AuthProvider, BearerAuthProvider, build_provider
from xaip.core.assertions import AssertionEngine
from xaip.core.extractor import ValueExtractor
from xaip.core.models import (
    Collection,
    CollectionStep,
    Environment,
    RunResult,
    StepResult,
    StepStatus,
)
from xaip.core.resolver import VariableResolver
from xaip.http.client import HttpClient


class CollectionRunner:
    """
    Ejecuta una colección completa respetando el grafo de dependencias.
    """

    def __init__(
        self,
        env: Environment,
        on_step_start: Callable[[str], None] | None = None,
        on_step_end: Callable[[StepResult], None] | None = None,
    ) -> None:
        self._env = env
        self._on_step_start = on_step_start
        self._on_step_end = on_step_end
        self._assertion_engine = AssertionEngine()
        self._extractor = ValueExtractor()

    async def run(
        self,
        collection: Collection,
        *,
        stop_on_failure: bool = True,
        only: list[str] | None = None,
        skip: list[str] | None = None,
        from_step: str | None = None,
        extra_vars: dict[str, Any] | None = None,
    ) -> RunResult:
        t0 = time.monotonic()
        run_id = str(uuid.uuid4())[:8]

        # Resolver auth
        auth_provider = build_provider(self._env.auth)

        # Variables de entorno + extras
        env_vars = {**self._env.vars}
        if self._env.base_url:
            env_vars["baseUrl"] = self._env.base_url
        env_vars.update(extra_vars or {})

        resolver = VariableResolver(env_vars=env_vars)

        # Filtrar pasos
        steps = self._filter_steps(collection.steps, only, skip, from_step)

        # Topological sort por dependencias
        ordered = self._topological_sort(steps)

        results: dict[str, StepResult] = {}
        failed_ids: set[str] = set()

        for step in ordered:
            # Evaluar si debe ejecutarse
            if step.id in failed_ids and not step.always:
                result = StepResult(
                    id=step.id,
                    name=step.name,
                    status=StepStatus.SKIPPED,
                )
                results[step.id] = result
                if self._on_step_end:
                    self._on_step_end(result)
                continue

            # Evaluar --run-if
            if step.run_if and not self._eval_condition(step.run_if, results):
                result = StepResult(
                    id=step.id,
                    name=step.name,
                    status=StepStatus.SKIPPED,
                )
                results[step.id] = result
                if self._on_step_end:
                    self._on_step_end(result)
                continue

            if self._on_step_start:
                self._on_step_start(step.id)

            # Si el paso tiene --as-auth, actualizar el provider con el token guardado
            current_auth = auth_provider

            result = await self._execute_step(
                step, resolver, current_auth, env_vars, results
            )
            results[step.id] = result

            # Guardar variables de paso en resolver
            # Expone: {{stepId.varName}} y {{stepId.body.field}}
            step_data: dict = dict(result.saved)
            if result.response:
                step_data["body"] = result.response.get("body")
                step_data["status"] = result.response.get("status")
                step_data["headers"] = result.response.get("headers", {})
            resolver.set_step(step.id, step_data)
            for var_name, value in result.saved.items():
                resolver.set_session(var_name, value)

            # Si el paso es --as-auth, crear nuevo provider con el token
            if step.as_auth and result.saved.get("token"):
                token = result.saved["token"]
                auth_provider = BearerAuthProvider(str(token))

            if self._on_step_end:
                self._on_step_end(result)

            if result.status == StepStatus.FAILED and not step.always:
                # Marcar todos los dependientes como fallidos
                for s in steps:
                    if step.id in s.depends_on:
                        failed_ids.add(s.id)
                if stop_on_failure:
                    # Ejecutar teardown (--always) antes de parar
                    for remaining in ordered:
                        if remaining.id not in results and remaining.always:
                            tr = await self._execute_step(
                                remaining, resolver, auth_provider, env_vars, results
                            )
                            results[remaining.id] = tr
                    break

        step_results = [results.get(s.id) or StepResult(id=s.id, status=StepStatus.SKIPPED) for s in ordered]
        summary = self._summarize(step_results)
        exit_code = 0 if summary.get("failed", 0) == 0 else 1
        duration = int((time.monotonic() - t0) * 1000)

        return RunResult(
            id=run_id,
            collection=collection.id,
            env=self._env.name or "default",
            startedAt=datetime.utcnow(),
            duration=duration,
            steps=step_results,
            summary=summary,
            exitCode=exit_code,
        )

    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: CollectionStep,
        resolver: VariableResolver,
        auth: AuthProvider,
        env_vars: dict[str, Any],
        previous_results: dict[str, StepResult],
    ) -> StepResult:
        attempt = 0
        max_attempts = max(1, 1 + step.retry)
        last_result: StepResult | None = None

        while attempt < max_attempts:
            attempt += 1
            last_result = await self._single_request(step, resolver, auth)

            # Evaluar --retry-until si aplica
            if step.retry_until and last_result.response:
                body = last_result.response.get("body")
                status = last_result.response.get("status", 0)
                if self._eval_condition(step.retry_until, previous_results, body=body, status=status):
                    break
                if attempt < max_attempts:
                    delay = _parse_duration(step.retry_delay or "1s")
                    await asyncio.sleep(delay)
                    continue
            else:
                break

            if last_result.status == StepStatus.PASSED:
                break

        return last_result  # type: ignore[return-value]

    async def _single_request(
        self,
        step: CollectionStep,
        resolver: VariableResolver,
        auth: AuthProvider,
    ) -> StepResult:
        req = step.request
        t0 = time.monotonic()

        try:
            # Resolver variables en path, body, headers, params
            path = resolver.resolve(req.path)
            headers = {k: resolver.resolve(v) for k, v in req.headers.items()}
            params = {k: resolver.resolve(v) for k, v in req.params.items()}
            body = resolver.resolve(req.body)

            timeout = _parse_duration(step.timeout) if step.timeout else None
            client = HttpClient(
                base_url=self._env.base_url,
                auth_provider=auth,
                timeout=timeout or 30.0,
            )
            resp = await client.request(
                req.method.value,
                path,
                headers=headers,
                params=params,
                body=body,
                form=req.form,
            )

            # Evaluar aserciones
            assertion_results = [
                AssertionEngine().evaluate(
                    expr, resp.status, resp.headers, resp.body, resp.duration_ms
                )
                for expr in step.expect
            ]

            all_passed = all(a.passed for a in assertion_results)
            status = StepStatus.PASSED if all_passed else StepStatus.FAILED

            # Extraer variables --save
            extractor = ValueExtractor()
            saved: dict[str, Any] = {}
            for var_name, expr in step.save.items():
                saved[var_name] = extractor.extract(expr, resp.body, resp.headers, resp.status)

            return StepResult(
                id=step.id,
                name=step.name,
                status=status,
                request=resp.request_dict(),
                response=resp.to_dict(),
                assertions=assertion_results,
                saved=saved,
                duration_ms=resp.duration_ms,
            )
        except Exception as exc:
            duration = int((time.monotonic() - t0) * 1000)
            return StepResult(
                id=step.id,
                name=step.name,
                status=StepStatus.ERROR,
                error=str(exc),
                duration_ms=duration,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_steps(
        steps: list[CollectionStep],
        only: list[str] | None,
        skip: list[str] | None,
        from_step: str | None,
    ) -> list[CollectionStep]:
        result = steps
        if only:
            result = [s for s in result if s.id in only]
        if skip:
            result = [s for s in result if s.id not in skip]
        if from_step:
            ids = [s.id for s in result]
            if from_step in ids:
                idx = ids.index(from_step)
                result = result[idx:]
        return result

    @staticmethod
    def _topological_sort(steps: list[CollectionStep]) -> list[CollectionStep]:
        """Kahn's algorithm para ordenar por dependencias."""
        step_map = {s.id: s for s in steps}
        in_degree: dict[str, int] = {s.id: 0 for s in steps}
        children: dict[str, list[str]] = {s.id: [] for s in steps}

        for s in steps:
            for dep in s.depends_on:
                if dep in step_map:
                    in_degree[s.id] += 1
                    children[dep].append(s.id)

        queue = [s.id for s in steps if in_degree[s.id] == 0]
        ordered: list[CollectionStep] = []

        while queue:
            cur_id = queue.pop(0)
            ordered.append(step_map[cur_id])
            for child_id in children[cur_id]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        # Agregar pasos que no participaron en el DAG (sin dependencias reconocidas)
        ordered_ids = {s.id for s in ordered}
        for s in steps:
            if s.id not in ordered_ids:
                ordered.append(s)

        return ordered

    @staticmethod
    def _eval_condition(
        expr: str,
        results: dict[str, StepResult],
        body: Any = None,
        status: int = 0,
    ) -> bool:
        """Evalúa expresiones como 'importar-sat.body.cuentasNuevas > 0'."""
        # Patrón: <stepId>.<field> <op> <value>
        m = re.match(r'^([\w-]+)\.([\w.]+)\s*([><=!]+)\s*(.+)$', expr.strip())
        if not m:
            # Expresión simple sobre body/status
            try:
                return bool(eval(expr, {"body": body, "status": status}))  # noqa: S307
            except Exception:
                return True  # Por defecto ejecutar si no se puede evaluar

        step_id, field_path, op, expected_raw = m.groups()
        result = results.get(step_id)
        if not result or not result.response:
            return False

        value = result.response.get("body")
        for part in field_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break

        try:
            expected = json.loads(expected_raw)
        except Exception:
            expected = expected_raw.strip().strip('"\'')

        try:
            if op == "==":
                return value == expected
            if op == "!=":
                return value != expected
            if op == ">":
                return float(value) > float(expected)
            if op == "<":
                return float(value) < float(expected)
            if op == ">=":
                return float(value) >= float(expected)
            if op == "<=":
                return float(value) <= float(expected)
        except (TypeError, ValueError):
            return False
        return False

    @staticmethod
    def _summarize(steps: list[StepResult]) -> dict[str, int]:
        counts: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "total": 0}
        for s in steps:
            counts["total"] += 1
            key = s.status.value
            if key in counts:
                counts[key] += 1
        return counts


def _parse_duration(duration: str) -> float:
    """Convierte '2s', '500ms', '1m' a segundos (float)."""
    duration = duration.strip()
    if duration.endswith("ms"):
        return float(duration[:-2]) / 1000
    if duration.endswith("m"):
        return float(duration[:-1]) * 60
    if duration.endswith("s"):
        return float(duration[:-1])
    return float(duration)
