"""
Structured local JSON event logger for TechBin.

This module saves disposal events and future fault events as JSON files inside
the local logs directory.

Important:
    Local logging is not the same as analytics counting.
    Analytics should only count payloads where isEventAccepted == True.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import ensure_runtime_directories, settings
from app.logger import get_logger


logger = get_logger(__name__)


class EventLogError(RuntimeError):
    """Raised when an event payload cannot be saved safely."""


def _timestamp_for_filename() -> str:
    """
    Return a filesystem-safe timestamp.
    """

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _json_default(value: Any) -> Any:
    """
    Convert non-standard Python objects into JSON-safe values.
    """

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")

    if is_dataclass(value):
        return asdict(value)

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()

    if hasattr(value, "__fspath__"):
        return os.fspath(value)

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _ensure_payload_dict(payload: Any) -> dict[str, Any]:
    """
    Normalize supported payload objects into a dictionary.
    """

    if isinstance(payload, dict):
        normalized = payload

    elif is_dataclass(payload):
        normalized = asdict(payload)

    elif hasattr(payload, "to_dict") and callable(payload.to_dict):
        normalized = payload.to_dict()

    else:
        raise EventLogError(
            f"Event payload must be a dict, dataclass, or object with to_dict(), "
            f"got {type(payload).__name__}"
        )

    if not normalized:
        raise EventLogError("Event payload cannot be empty")

    return normalized


def _safe_prefix(prefix: str | None) -> str:
    """
    Build a safe filename prefix.
    """

    raw_prefix = prefix or settings.logging.event_file_prefix
    cleaned = raw_prefix.strip().lower().replace(" ", "_")

    safe_chars = []
    for char in cleaned:
        if char.isalnum() or char in ("_", "-"):
            safe_chars.append(char)

    safe = "".join(safe_chars).strip("_-")

    return safe or "event"


def build_event_log_path(
    prefix: str | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    """
    Build a timestamped JSON log path.
    """

    directory = Path(output_dir) if output_dir is not None else settings.logs_dir
    filename = f"{_safe_prefix(prefix)}_{_timestamp_for_filename()}.json"

    return directory / filename


def save_event_log(
    payload: Any,
    output_dir: str | Path | None = None,
    prefix: str | None = None,
    filename: str | None = None,
) -> Path:
    """
    Save an event payload as a JSON file.

    Args:
        payload:
            Event dictionary, dataclass, or object with to_dict().

        output_dir:
            Optional custom output directory. Defaults to logs/.

        prefix:
            Optional filename prefix. Defaults to settings.logging.event_file_prefix.

        filename:
            Optional exact filename. If provided, it must end with .json.

    Returns:
        Path to the saved JSON file.

    Compatibility:
        Older prototype scripts can still call:
            save_event_log(payload)
    """

    ensure_runtime_directories()

    payload_dict = _ensure_payload_dict(payload)

    directory = Path(output_dir) if output_dir is not None else settings.logs_dir
    directory.mkdir(parents=True, exist_ok=True)

    if filename is not None:
        clean_filename = filename.strip()

        if clean_filename == "":
            raise EventLogError("filename cannot be empty")

        if not clean_filename.endswith(".json"):
            clean_filename = f"{clean_filename}.json"

        final_path = directory / clean_filename
    else:
        final_path = build_event_log_path(prefix=prefix, output_dir=directory)

    final_path = final_path.resolve()
    temp_path = final_path.with_suffix(final_path.suffix + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                payload_dict,
                file,
                indent=2,
                ensure_ascii=False,
                default=_json_default,
            )
            file.write("\n")

        temp_path.replace(final_path)

        logger.info("Event log saved: %s", final_path)

        return final_path

    except Exception as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

        raise EventLogError(f"Failed to save event log to {final_path}") from exc


def load_event_log(path: str | Path) -> dict[str, Any]:
    """
    Load one event JSON file.
    """

    log_path = Path(path)

    if not log_path.exists():
        raise EventLogError(f"Event log file does not exist: {log_path}")

    try:
        with log_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

    except Exception as exc:
        raise EventLogError(f"Failed to read event log: {log_path}") from exc

    if not isinstance(data, dict):
        raise EventLogError(f"Event log does not contain a JSON object: {log_path}")

    return data


# Backward-compatible aliases.
save_json_event = save_event_log
write_event_log = save_event_log


__all__ = [
    "EventLogError",
    "build_event_log_path",
    "save_event_log",
    "save_json_event",
    "write_event_log",
    "load_event_log",
]
