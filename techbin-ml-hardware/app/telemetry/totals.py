"""
Persistent local totals for TechBin Supabase telemetry.

The cloud contract expects full current totals. This module keeps those totals
locally so retrying the same event does not depend on increment commands.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.config import ensure_runtime_directories, settings
from app.ml.effnetv2 import REAL_MODEL_CATEGORIES, RECYCLABLE_CATEGORIES


class TotalsStoreError(RuntimeError):
    """Raised when persistent totals cannot be loaded or saved."""


@dataclass(frozen=True)
class DisposalTotals:
    totalItems: int = 0
    cardboard: int = 0
    paper: int = 0
    plastic_glass: int = 0
    metal: int = 0
    trash: int = 0
    recyclableItems: int = 0
    nonRecyclableItems: int = 0
    correctDisposals: int = 0
    incorrectDisposals: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


DEFAULT_TOTALS = DisposalTotals().to_dict()


def _coerce_totals(data: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}

    for key, default_value in DEFAULT_TOTALS.items():
        value = data.get(key, default_value)

        try:
            int_value = int(value)
        except (TypeError, ValueError):
            int_value = default_value

        totals[key] = max(0, int_value)

    return totals


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")

        temp_path.replace(path)

    except Exception as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

        raise TotalsStoreError(f"Failed to write totals file: {path}") from exc


class LocalTotalsStore:
    """
    JSON-backed persistent totals store.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        ensure_runtime_directories()
        self.path = (
            Path(path).expanduser().resolve()
            if path is not None
            else settings.logs_dir / "supabase_totals.json"
        )

    def load(self) -> dict[str, int]:
        if not self.path.exists():
            return DEFAULT_TOTALS.copy()

        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            raise TotalsStoreError(f"Failed to read totals file: {self.path}") from exc

        if not isinstance(data, dict):
            raise TotalsStoreError(f"Totals file is not a JSON object: {self.path}")

        return _coerce_totals(data)

    def save(self, totals: dict[str, Any]) -> dict[str, int]:
        normalized = _coerce_totals(totals)
        _write_json_atomic(self.path, normalized)
        return normalized

    def update_for_confirmed_event(
        self,
        *,
        category: str,
        correct: bool,
    ) -> dict[str, int]:
        if category not in REAL_MODEL_CATEGORIES:
            raise TotalsStoreError(f"Unsupported category for totals: {category}")

        totals = self.load()
        totals["totalItems"] += 1
        totals[category] += 1

        if category in RECYCLABLE_CATEGORIES:
            totals["recyclableItems"] += 1
        else:
            totals["nonRecyclableItems"] += 1

        if correct:
            totals["correctDisposals"] += 1
        else:
            totals["incorrectDisposals"] += 1

        return self.save(totals)


__all__ = [
    "TotalsStoreError",
    "DisposalTotals",
    "DEFAULT_TOTALS",
    "LocalTotalsStore",
]
