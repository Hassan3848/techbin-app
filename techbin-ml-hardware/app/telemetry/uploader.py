"""
Telemetry uploader for TechBin.

Current stage:
    Safe local queue + dry-run upload.

Why this exists now:
    The real backend/Firebase upload method is not finalized yet, but the device
    runtime should already have a production-style telemetry boundary.

Current behavior:
    - validate payload dictionary
    - save payloads to local pending queue
    - dry-run upload without network
    - optional HTTP JSON transport for later backend endpoint
    - move successfully uploaded payloads to sent/
    - move permanently failed payloads to failed/

Folder structure:
    logs/telemetry_queue/
        pending/
        sent/
        failed/
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from app.config import ensure_runtime_directories, settings
from app.logger import get_logger


logger = get_logger(__name__)


class TelemetryUploadError(RuntimeError):
    """Raised when telemetry upload or queue handling fails."""


@dataclass(frozen=True)
class TransportResponse:
    """
    Response returned by a telemetry transport.
    """

    ok: bool
    status_code: int | None
    message: str
    response_body: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UploadResult:
    """
    Result returned after queue/upload operation.
    """

    payload_id: str
    status: str
    message: str
    queue_path: str | None = None
    response_status_code: int | None = None
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelemetryTransport(Protocol):
    """
    Interface for telemetry transports.

    Later we can implement:
        - Firebase transport
        - backend REST transport
        - MQTT transport
    """

    def send(self, payload: dict[str, Any]) -> TransportResponse:
        """Send one payload."""


class DryRunTransport:
    """
    Safe transport that does not contact any backend.

    This is ideal for development and demo testing before real sync is enabled.
    """

    def send(self, payload: dict[str, Any]) -> TransportResponse:
        event_type = payload.get("eventType", "unknown_event")

        return TransportResponse(
            ok=True,
            status_code=200,
            message=f"dry_run_success:{event_type}",
            response_body=None,
        )


class HttpJsonTransport:
    """
    Simple HTTP JSON transport for future backend integration.

    This is not required yet. Use only when you have a real endpoint.
    """

    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = 10.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        if not isinstance(endpoint_url, str) or endpoint_url.strip() == "":
            raise TelemetryUploadError("endpoint_url cannot be empty")

        self.endpoint_url = endpoint_url.strip()
        self.timeout_seconds = timeout_seconds
        self.headers = headers or {}

    def send(self, payload: dict[str, Any]) -> TransportResponse:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request_headers = {
            "Content-Type": "application/json",
            **self.headers,
        }

        request = urllib.request.Request(
            self.endpoint_url,
            data=body,
            headers=request_headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                status_code = int(response.status)

            return TransportResponse(
                ok=200 <= status_code < 300,
                status_code=status_code,
                message="http_upload_completed",
                response_body=response_body,
            )

        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")

            return TransportResponse(
                ok=False,
                status_code=exc.code,
                message=f"http_error:{exc.reason}",
                response_body=response_body,
            )

        except urllib.error.URLError as exc:
            return TransportResponse(
                ok=False,
                status_code=None,
                message=f"url_error:{exc.reason}",
                response_body=None,
            )

        except Exception as exc:
            return TransportResponse(
                ok=False,
                status_code=None,
                message=f"unexpected_http_error:{exc}",
                response_body=None,
            )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _json_default(value: Any) -> Any:
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
    if isinstance(payload, dict):
        normalized = payload

    elif is_dataclass(payload):
        normalized = asdict(payload)

    elif hasattr(payload, "to_dict") and callable(payload.to_dict):
        normalized = payload.to_dict()

    else:
        raise TelemetryUploadError(
            f"payload must be dict, dataclass, or object with to_dict(), "
            f"got {type(payload).__name__}"
        )

    if not normalized:
        raise TelemetryUploadError("payload cannot be empty")

    return normalized


def _safe_name(value: str | None, fallback: str) -> str:
    raw = value or fallback
    cleaned = raw.strip().lower().replace(" ", "_")

    chars = []
    for char in cleaned:
        if char.isalnum() or char in ("_", "-"):
            chars.append(char)

    safe = "".join(chars).strip("_-")
    return safe or fallback


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as exc:
        raise TelemetryUploadError(f"Failed to load JSON file: {path}") from exc

    if not isinstance(data, dict):
        raise TelemetryUploadError(f"JSON file does not contain an object: {path}")

    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
                default=_json_default,
            )
            file.write("\n")

        temp_path.replace(path)

    except Exception as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

        raise TelemetryUploadError(f"Failed to write JSON file: {path}") from exc


def _move_file_unique(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / source.name

    if destination.exists():
        destination = destination_dir / f"{source.stem}_{uuid4().hex[:8]}{source.suffix}"

    shutil.move(str(source), str(destination))
    return destination


class TelemetryUploader:
    """
    Queue-based telemetry uploader.

    Safe default:
        Uses DryRunTransport, so no network call happens unless you explicitly
        provide another transport.
    """

    def __init__(
        self,
        transport: TelemetryTransport | None = None,
        queue_root: str | Path | None = None,
        max_retries: int = 3,
    ) -> None:
        if max_retries < 1:
            raise TelemetryUploadError("max_retries must be at least 1")

        ensure_runtime_directories()

        self.transport = transport or DryRunTransport()
        self.queue_root = (
            Path(queue_root).expanduser().resolve()
            if queue_root is not None
            else settings.logs_dir / "telemetry_queue"
        )
        self.pending_dir = self.queue_root / "pending"
        self.sent_dir = self.queue_root / "sent"
        self.failed_dir = self.queue_root / "failed"
        self.max_retries = max_retries

        self.ensure_queue_dirs()

    def ensure_queue_dirs(self) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    def build_envelope(
        self,
        payload: Any,
        payload_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Wrap raw payload with queue metadata.
        """

        payload_dict = _ensure_payload_dict(payload)

        return {
            "payloadId": payload_id or uuid4().hex,
            "createdAt": _now_iso(),
            "updatedAt": _now_iso(),
            "attempts": 0,
            "lastError": None,
            "payload": payload_dict,
        }

    def enqueue(
        self,
        payload: Any,
        prefix: str | None = None,
        payload_id: str | None = None,
    ) -> Path:
        """
        Save payload to local pending telemetry queue.
        """

        envelope = self.build_envelope(payload, payload_id=payload_id)

        event_type = envelope["payload"].get("eventType", "telemetry")
        safe_prefix = _safe_name(prefix or str(event_type), "telemetry")

        filename = f"{safe_prefix}_{_timestamp_for_filename()}_{envelope['payloadId']}.json"
        path = self.pending_dir / filename

        _write_json_atomic(path, envelope)

        logger.info("Telemetry payload queued: %s", path)

        return path

    def upload_payload(
        self,
        payload: Any,
        payload_id: str | None = None,
    ) -> UploadResult:
        """
        Try uploading one payload immediately.
        """

        payload_dict = _ensure_payload_dict(payload)
        active_payload_id = payload_id or uuid4().hex

        response = self.transport.send(payload_dict)

        if response.ok:
            logger.info(
                "Telemetry payload uploaded | payload_id=%s | status=%s | message=%s",
                active_payload_id,
                response.status_code,
                response.message,
            )

            return UploadResult(
                payload_id=active_payload_id,
                status="sent",
                message=response.message,
                response_status_code=response.status_code,
                attempts=1,
            )

        logger.warning(
            "Telemetry upload failed | payload_id=%s | status=%s | message=%s",
            active_payload_id,
            response.status_code,
            response.message,
        )

        return UploadResult(
            payload_id=active_payload_id,
            status="failed",
            message=response.message,
            response_status_code=response.status_code,
            attempts=1,
        )

    def upload_or_queue(
        self,
        payload: Any,
        prefix: str | None = None,
        payload_id: str | None = None,
    ) -> UploadResult:
        """
        Try upload immediately. If it fails, queue locally.
        """

        active_payload_id = payload_id or uuid4().hex
        result = self.upload_payload(payload, payload_id=active_payload_id)

        if result.status == "sent":
            return result

        queue_path = self.enqueue(payload, prefix=prefix, payload_id=active_payload_id)

        return UploadResult(
            payload_id=active_payload_id,
            status="queued",
            message=f"upload_failed_then_queued:{result.message}",
            queue_path=str(queue_path),
            response_status_code=result.response_status_code,
            attempts=result.attempts,
        )

    def upload_pending_file(self, path: str | Path) -> UploadResult:
        """
        Upload one pending queue file.
        """

        pending_path = Path(path).expanduser().resolve()

        if not pending_path.exists():
            raise TelemetryUploadError(f"Pending file does not exist: {pending_path}")

        envelope = _load_json(pending_path)

        payload_id = str(envelope.get("payloadId") or uuid4().hex)
        attempts = int(envelope.get("attempts") or 0)
        payload = envelope.get("payload")

        if not isinstance(payload, dict):
            raise TelemetryUploadError(f"Pending file has invalid payload: {pending_path}")

        if attempts >= self.max_retries:
            failed_path = _move_file_unique(pending_path, self.failed_dir)

            return UploadResult(
                payload_id=payload_id,
                status="failed",
                message="max_retries_exceeded",
                queue_path=str(failed_path),
                attempts=attempts,
            )

        response = self.transport.send(payload)
        attempts += 1

        envelope["attempts"] = attempts
        envelope["updatedAt"] = _now_iso()

        if response.ok:
            envelope["sentAt"] = _now_iso()
            envelope["lastError"] = None
            _write_json_atomic(pending_path, envelope)
            sent_path = _move_file_unique(pending_path, self.sent_dir)

            logger.info("Pending telemetry uploaded: %s", sent_path)

            return UploadResult(
                payload_id=payload_id,
                status="sent",
                message=response.message,
                queue_path=str(sent_path),
                response_status_code=response.status_code,
                attempts=attempts,
            )

        envelope["lastError"] = response.message
        _write_json_atomic(pending_path, envelope)

        if attempts >= self.max_retries:
            failed_path = _move_file_unique(pending_path, self.failed_dir)

            logger.warning("Pending telemetry moved to failed: %s", failed_path)

            return UploadResult(
                payload_id=payload_id,
                status="failed",
                message=response.message,
                queue_path=str(failed_path),
                response_status_code=response.status_code,
                attempts=attempts,
            )

        logger.warning(
            "Pending telemetry upload failed, kept pending: %s",
            pending_path,
        )

        return UploadResult(
            payload_id=payload_id,
            status="pending",
            message=response.message,
            queue_path=str(pending_path),
            response_status_code=response.status_code,
            attempts=attempts,
        )

    def upload_pending(self) -> list[UploadResult]:
        """
        Upload all JSON files from pending queue.
        """

        self.ensure_queue_dirs()

        pending_files = sorted(self.pending_dir.glob("*.json"))

        results: list[UploadResult] = []

        for path in pending_files:
            try:
                results.append(self.upload_pending_file(path))
            except Exception as exc:
                logger.error("Failed to upload pending file %s: %s", path, exc)

                results.append(
                    UploadResult(
                        payload_id="unknown",
                        status="failed",
                        message=str(exc),
                        queue_path=str(path),
                        attempts=0,
                    )
                )

        return results


__all__ = [
    "TelemetryUploadError",
    "TransportResponse",
    "UploadResult",
    "TelemetryTransport",
    "DryRunTransport",
    "HttpJsonTransport",
    "TelemetryUploader",
]
