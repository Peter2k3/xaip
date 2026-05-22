"""
Gestión de persistencia del archivo .xaip.json
Pattern: Repository
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from xaip.core.models import XaipConfig, Environment

XAIP_FILE = ".xaip.json"


class ConfigRepository:
    """Lee y escribe el .xaip.json del workspace."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or self._find_config()

    # ------------------------------------------------------------------
    # Localización del archivo
    # ------------------------------------------------------------------

    @staticmethod
    def _find_config(start: Path | None = None) -> Path:
        current = start or Path.cwd()
        for directory in [current, *current.parents]:
            candidate = directory / XAIP_FILE
            if candidate.exists():
                return candidate
        return Path.cwd() / XAIP_FILE  # default: cwd (puede no existir aún)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def load(self) -> XaipConfig:
        if not self._path.exists():
            raise FileNotFoundError(
                f"No se encontró {XAIP_FILE}. Ejecuta 'xaip init' primero."
            )
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        try:
            return XaipConfig.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f".xaip.json inválido:\n{exc}") from exc

    def save(self, config: XaipConfig) -> None:
        data = config.model_dump(by_alias=True, exclude_none=True)
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )

    def create(self, config: XaipConfig) -> None:
        if self._path.exists():
            raise FileExistsError(f"{self._path} ya existe.")
        self.save(config)

    # ------------------------------------------------------------------
    # Helpers de mutación atómica
    # ------------------------------------------------------------------

    def update(self, mutator: Any) -> XaipConfig:
        """Carga, aplica mutator(config) y guarda."""
        cfg = self.load()
        mutator(cfg)
        self.save(cfg)
        return cfg


def _json_default(obj: Any) -> Any:
    from datetime import datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"No serializable: {type(obj)}")
