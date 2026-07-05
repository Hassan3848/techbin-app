"""
Telemetry payload builders for TechBin.

This module converts validated device-side events into structured dictionaries
that can be saved locally and later synced to the backend/dashboard.

Important rule:
    Payload creation must use the disposal validator so expectedSide,
    recyclability, correctness, and confidence acceptance remain consistent.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.engine.disposal_validator import (
    DisposalValidationResult,
    validate_disposal,
)


class PayloadBuildError(ValueError):
    """Raised when a telemetry payload cannot be built safely."""


@dataclass(frozen=True)
class DisposalEventPayload:
    """
    Structured disposal event payload.

    This shape is intentionally close to the JSON that will later be sent
    to Firebase/backend.
    """

    timestamp: str
    binId: str
    orgId: str
    eventType: str
    predictedClass: str
    recyclability: str
    confidence: float
    imagePath: str
    disposalSide: str
    expectedSide: str
    isCorrectDisposal: bool
    isConfidenceAccepted: bool
    isEventAccepted: bool
    rejectionReason: str | None
    source: str
    schemaVersion: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert payload dataclass to a JSON-safe dictionary.
        """

        return asdict(self)


@dataclass(frozen=True)
class FaultPayload:
    """
    Structured device fault payload.

    This will be used more heavily when we add fault monitoring later.
    """

    timestamp: str
    binId: str
    orgId: str
    faultCode: str
    severity: str
    message: str
    component: str
    isResolved: bool
    source: str
    schemaVersion: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    """
    Return current local timestamp as ISO string.
    """

    return datetime.now().isoformat(timespec="microseconds")


def _normalize_image_path(image_path: Any) -> str:
    """
    Convert image path input to a clean string.

    Supported inputs:
        - str
        - pathlib.Path
        - Camera CaptureResult object with .image_path
        - filesystem path-like object using __fspath__

    This keeps old prototype tests working while still producing a clean
    production payload.
    """

    if hasattr(image_path, "image_path"):
        image_path = getattr(image_path, "image_path")

    if isinstance(image_path, Path):
        value = str(image_path.resolve())

    elif isinstance(image_path, str):
        value = image_path.strip()

    elif hasattr(image_path, "__fspath__"):
        value = os.fspath(image_path).strip()

    else:
        raise PayloadBuildError(
            f"image_path must be str, Path, path-like, or CaptureResult, "
            f"got {type(image_path).__name__}"
        )

    if value == "":
        raise PayloadBuildError("image_path cannot be empty")

    return value


def _normalize_source(source: str) -> str:
    """
    Normalize event source name.
    """

    if not isinstance(source, str):
        raise PayloadBuildError(
            f"source must be a string, got {type(source).__name__}"
        )

    normalized = source.strip()

    if normalized == "":
        raise PayloadBuildError("source cannot be empty")

    return normalized


def build_disposal_event_payload(
    predicted_class: str,
    confidence: float,
    image_path: Any,
    disposal_side: str,
    source: str = "device_runtime",
    timestamp: str | None = None,
    bin_id: str | None = None,
    org_id: str | None = None,
    min_confidence: float | None = None,
) -> dict[str, Any]:
    """
    Build a validated disposal event payload.

    Event acceptance:
        If confidence is below threshold, payload is still built for debugging,
        but isEventAccepted will be False.

    Analytics rule:
        Dashboard/backend should only count events where isEventAccepted is True.
    """

    validation: DisposalValidationResult = validate_disposal(
        predicted_class=predicted_class,
        confidence=confidence,
        disposal_side=disposal_side,
        min_confidence=(
            settings.ml.min_confidence
            if min_confidence is None
            else min_confidence
        ),
    )

    payload = DisposalEventPayload(
        timestamp=timestamp or _now_iso(),
        binId=bin_id or settings.device.bin_id,
        orgId=org_id or settings.device.org_id,
        eventType="disposal_event",
        predictedClass=validation.predicted_class,
        recyclability=validation.recyclability,
        confidence=validation.confidence,
        imagePath=_normalize_image_path(image_path),
        disposalSide=validation.disposal_side,
        expectedSide=validation.expected_side,
        isCorrectDisposal=validation.is_correct_disposal,
        isConfidenceAccepted=validation.is_confidence_accepted,
        isEventAccepted=validation.is_event_accepted,
        rejectionReason=validation.rejection_reason,
        source=_normalize_source(source),
    )

    return payload.to_dict()


def build_fault_payload(
    fault_code: str,
    severity: str,
    message: str,
    component: str,
    source: str = "device_runtime",
    timestamp: str | None = None,
    bin_id: str | None = None,
    org_id: str | None = None,
    is_resolved: bool = False,
) -> dict[str, Any]:
    """
    Build a device fault payload.

    Later this will report:
        camera failure
        inference failure
        ultrasonic failure
        metal sensor failure
        network failure
        audio failure
    """

    if not isinstance(fault_code, str) or fault_code.strip() == "":
        raise PayloadBuildError("fault_code cannot be empty")

    if not isinstance(severity, str) or severity.strip() == "":
        raise PayloadBuildError("severity cannot be empty")

    if not isinstance(message, str) or message.strip() == "":
        raise PayloadBuildError("message cannot be empty")

    if not isinstance(component, str) or component.strip() == "":
        raise PayloadBuildError("component cannot be empty")

    normalized_severity = severity.strip().lower()

    if normalized_severity not in ("info", "warning", "critical"):
        raise PayloadBuildError(
            "severity must be one of: info, warning, critical"
        )

    payload = FaultPayload(
        timestamp=timestamp or _now_iso(),
        binId=bin_id or settings.device.bin_id,
        orgId=org_id or settings.device.org_id,
        faultCode=fault_code.strip(),
        severity=normalized_severity,
        message=message.strip(),
        component=component.strip(),
        isResolved=bool(is_resolved),
        source=_normalize_source(source),
    )

    return payload.to_dict()


def build_event_payload(
    predicted_class: str,
    confidence: float,
    image_path: Any,
    disposal_side: str,
    source: str = "manual_test",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Backward-compatible alias for older manual event flow scripts.
    """

    return build_disposal_event_payload(
        predicted_class=predicted_class,
        confidence=confidence,
        image_path=image_path,
        disposal_side=disposal_side,
        source=source,
        **kwargs,
    )


build_manual_event_payload = build_event_payload


__all__ = [
    "PayloadBuildError",
    "DisposalEventPayload",
    "FaultPayload",
    "build_disposal_event_payload",
    "build_event_payload",
    "build_manual_event_payload",
    "build_fault_payload",
]
