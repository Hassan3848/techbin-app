"""
Supabase ingest payloads and transport for TechBin Pi.

This module implements docs/WEB_CLOUD_CONTRACT_FOR_PI.md. It does not own a
separate queue; callers should use TelemetryUploader with this transport.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import settings
from app.ml.effnetv2 import REAL_MODEL_CATEGORIES, RECYCLABLE_CATEGORIES
from app.telemetry.totals import DEFAULT_TOTALS
from app.telemetry.uploader import HttpJsonTransport, TelemetryUploadError


SUPABASE_SIDE_RECYCLABLE = "recyclable"
SUPABASE_SIDE_NON_RECYCLABLE = "non_recyclable"
VALID_SUPABASE_SIDES = (SUPABASE_SIDE_RECYCLABLE, SUPABASE_SIDE_NON_RECYCLABLE)


class SupabasePayloadError(ValueError):
    """Raised when a Supabase payload cannot be built safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_event_id(bin_code: str | None = None) -> str:
    clean_bin_code = (bin_code or settings.supabase.bin_code or "BIN-001").strip()
    compact_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"pi-{clean_bin_code}-{compact_time}-{uuid4().hex}"


def category_is_recyclable(category: str) -> bool:
    if category not in REAL_MODEL_CATEGORIES:
        raise SupabasePayloadError(f"Unsupported category: {category}")

    return category in RECYCLABLE_CATEGORIES


def expected_side_for_category(category: str) -> str:
    return (
        SUPABASE_SIDE_RECYCLABLE
        if category_is_recyclable(category)
        else SUPABASE_SIDE_NON_RECYCLABLE
    )


def physical_side_to_supabase(side: str) -> str:
    normalized = side.strip().lower().replace("-", "_")

    aliases = {
        "right": SUPABASE_SIDE_RECYCLABLE,
        "r": SUPABASE_SIDE_RECYCLABLE,
        "recyclable": SUPABASE_SIDE_RECYCLABLE,
        "left": SUPABASE_SIDE_NON_RECYCLABLE,
        "l": SUPABASE_SIDE_NON_RECYCLABLE,
        "non_recyclable": SUPABASE_SIDE_NON_RECYCLABLE,
        "nonrecyclable": SUPABASE_SIDE_NON_RECYCLABLE,
        "non recyclable": SUPABASE_SIDE_NON_RECYCLABLE,
    }

    mapped = aliases.get(normalized)
    if mapped is None:
        raise SupabasePayloadError(f"Unsupported disposal side: {side}")

    return mapped


def _percent_or_none(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def extract_capacity_sensor_payload(capacity_result: Any) -> dict[str, int | None]:
    """
    Convert DualCapacityMonitorResult-like data to cloud sensor fields.
    """

    if capacity_result is None:
        return {
            "leftFillLevel": None,
            "rightFillLevel": None,
            "fillLevel": None,
            "temperature": None,
            "gasLevel": None,
        }

    data = (
        capacity_result.to_dict()
        if hasattr(capacity_result, "to_dict")
        else capacity_result
    )

    if not isinstance(data, dict):
        raise SupabasePayloadError("capacity_result must be a dict or to_dict object")

    left_fill = ((data.get("left") or {}).get("fillLevel") or {}).get("fillPercentage")
    right_fill = ((data.get("right") or {}).get("fillLevel") or {}).get("fillPercentage")

    left_percent = _percent_or_none(left_fill)
    right_percent = _percent_or_none(right_fill)
    valid_values = [
        value for value in (left_percent, right_percent) if value is not None
    ]
    overall = max(valid_values) if valid_values else None

    return {
        "leftFillLevel": left_percent,
        "rightFillLevel": right_percent,
        "fillLevel": overall,
        "temperature": None,
        "gasLevel": None,
    }


def build_faults_payload(
    *,
    camera: bool = False,
    ultrasonic: bool = False,
    metal: bool = False,
    network: bool = False,
    servo: bool | None = None,
    motor: bool | None = None,
    ir: bool | None = None,
) -> dict[str, bool | None]:
    faults: dict[str, bool | None] = {
        "camera": bool(camera),
        "ultrasonic": bool(ultrasonic),
        "metal": bool(metal),
        "network": bool(network),
    }

    if servo is not None:
        faults["servo"] = bool(servo)
    if motor is not None:
        faults["motor"] = bool(motor)
    if ir is not None:
        faults["ir"] = bool(ir)

    return faults


def normalize_statistics(statistics: dict[str, Any] | None) -> dict[str, int]:
    source = statistics or {}
    normalized: dict[str, int] = {}

    for key, default_value in DEFAULT_TOTALS.items():
        try:
            value = int(source.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value

        normalized[key] = max(0, value)

    return normalized


def build_latest_event(
    *,
    event_id: str,
    category: str,
    disposed_side: str,
    confidence: float,
    timestamp: str | None = None,
    model_version: str | None = None,
    classification_source: str = "camera",
    label: str | None = None,
    placement_confirmed: bool = True,
    image_url: str | None = None,
) -> dict[str, Any]:
    if category not in REAL_MODEL_CATEGORIES:
        raise SupabasePayloadError(f"Unsupported category: {category}")

    expected_side = expected_side_for_category(category)
    normalized_disposed_side = (
        disposed_side
        if disposed_side in VALID_SUPABASE_SIDES
        else physical_side_to_supabase(disposed_side)
    )

    return {
        "eventId": event_id,
        "timestamp": timestamp or utc_now_iso(),
        "label": label or category,
        "category": category,
        "recyclable": category_is_recyclable(category),
        "expectedSide": expected_side,
        "disposedSide": normalized_disposed_side,
        "correct": normalized_disposed_side == expected_side,
        "confidence": float(confidence),
        "placementConfirmed": bool(placement_confirmed),
        "modelVersion": model_version or settings.ml.model_version,
        "classificationSource": classification_source,
        "imageUrl": image_url,
    }


def build_metal_sensor_override_event(
    *,
    event_id: str,
    disposed_side: str,
    confidence: float = 1.0,
    timestamp: str | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """
    Build a future metal-sensor override event.

    This is disabled by default through TECHBIN_ENABLE_METAL_OVERRIDE. The real
    metal sensor GPIO is also disabled in pin_map.py.
    """

    if not settings.device.metal_override_enabled:
        raise SupabasePayloadError(
            "Metal override is disabled. Set TECHBIN_ENABLE_METAL_OVERRIDE=1 only after hardware validation."
        )

    return build_latest_event(
        event_id=event_id,
        timestamp=timestamp,
        category="metal",
        disposed_side=disposed_side,
        confidence=confidence,
        model_version=model_version,
        classification_source="metal_sensor",
        label="metal",
        placement_confirmed=True,
        image_url=None,
    )


def build_bin_state_payload(
    *,
    statistics: dict[str, Any] | None = None,
    sensors: dict[str, Any] | None = None,
    faults: dict[str, Any] | None = None,
    latest_event: dict[str, Any] | None = None,
    status_state: str = "normal",
    status_message: str = "Running",
    org_id: str | None = None,
    bin_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "orgId": org_id or settings.device.org_id,
        "binCode": bin_code or settings.supabase.bin_code,
        "status": {
            "state": status_state,
            "message": status_message,
        },
        "sensors": sensors
        or {
            "leftFillLevel": None,
            "rightFillLevel": None,
            "fillLevel": None,
            "temperature": None,
            "gasLevel": None,
        },
        "statistics": normalize_statistics(statistics),
        "faults": faults or build_faults_payload(),
    }

    if latest_event is not None:
        if not isinstance(latest_event, dict):
            raise SupabasePayloadError("latest_event must be a dict")
        if not latest_event.get("eventId"):
            raise SupabasePayloadError("latest_event.eventId is required")

        payload["latestEvent"] = latest_event

    return payload


def build_heartbeat_payload(
    *,
    statistics: dict[str, Any] | None = None,
    sensors: dict[str, Any] | None = None,
    faults: dict[str, Any] | None = None,
    status_message: str = "Heartbeat",
) -> dict[str, Any]:
    return build_bin_state_payload(
        statistics=statistics,
        sensors=sensors,
        faults=faults,
        latest_event=None,
        status_state="normal",
        status_message=status_message,
    )


def build_supabase_ingest_url(base_url: str | None = None) -> str:
    raw_url = (base_url or settings.supabase.url).strip()
    if raw_url == "":
        raise SupabasePayloadError("TECHBIN_SUPABASE_URL is required")

    return raw_url.rstrip("/") + "/functions/v1/ingest-bin-state"


def build_supabase_transport() -> HttpJsonTransport:
    if settings.supabase.device_token.strip() == "":
        raise TelemetryUploadError("TECHBIN_DEVICE_TOKEN is required")

    return HttpJsonTransport(
        endpoint_url=build_supabase_ingest_url(),
        timeout_seconds=settings.supabase.timeout_seconds,
        headers={"x-device-token": settings.supabase.device_token},
    )


__all__ = [
    "SUPABASE_SIDE_RECYCLABLE",
    "SUPABASE_SIDE_NON_RECYCLABLE",
    "VALID_SUPABASE_SIDES",
    "SupabasePayloadError",
    "utc_now_iso",
    "new_event_id",
    "category_is_recyclable",
    "expected_side_for_category",
    "physical_side_to_supabase",
    "extract_capacity_sensor_payload",
    "build_faults_payload",
    "normalize_statistics",
    "build_latest_event",
    "build_metal_sensor_override_event",
    "build_bin_state_payload",
    "build_heartbeat_payload",
    "build_supabase_ingest_url",
    "build_supabase_transport",
]
