"""
Registry de scanners — detecta automáticamente el stack del proyecto.
Pattern: Registry + Chain of Responsibility
"""
from __future__ import annotations

from pathlib import Path

from xaip.core.models import EndpointSchema
from xaip.scanners.base import BaseScanner
from xaip.scanners.spring_boot import SpringBootScanner
from xaip.scanners.fastapi import FastApiScanner

_REGISTRY: list[BaseScanner] = [
    SpringBootScanner(),
    FastApiScanner(),
]


def detect_stack(root: Path) -> BaseScanner | None:
    for scanner in _REGISTRY:
        if scanner.can_handle(root):
            return scanner
    return None


def get_scanner(name: str) -> BaseScanner | None:
    return next((s for s in _REGISTRY if s.name == name), None)


def list_stacks() -> list[str]:
    return [s.name for s in _REGISTRY]
