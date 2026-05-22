"""
Interfaz base para scanners de distintos stacks.
Pattern: Template Method + Strategy
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from xaip.core.models import EndpointSchema


class BaseScanner(ABC):
    @abstractmethod
    def can_handle(self, root: Path) -> bool:
        """Devuelve True si este scanner puede manejar el proyecto."""

    @abstractmethod
    def scan(self, root: Path) -> list[EndpointSchema]:
        """Escanea y devuelve la lista de endpoints."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del stack (ej: 'spring-boot')."""
