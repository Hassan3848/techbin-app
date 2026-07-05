"""
Confidence engine for TechBin disposal events.

Purpose:
    Decide whether an event is trustworthy enough to be counted in analytics.

Current stage:
    Uses ML confidence and validated disposal result.

Future stage:
    Will also use:
        - front ultrasonic session trigger
        - left/right compartment confirmation
        - Omron metal sensor signal
        - image quality checks
        - model uncertainty checks

Important product rules:
    1. A camera capture alone is not a disposal event.
    2. A compartment disturbance alone is not a disposal event.
    3. Analytics must only update after confidence checks pass.
    4. Metal sensor is only a confidence booster, not the sole truth source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.config import MIN_CONFIDENCE
from app.engine.disposal_validator import DisposalValidationResult
from app.logger import get_logger


logger = get_logger(__name__)


class ConfidenceEngineError(ValueError):
    """Raised when confidence evaluation input is invalid."""


@dataclass(frozen=True)
class ConfidenceDecision:
    """
    Final confidence decision for one event.

    is_event_accepted:
        True only when the event is safe to count in analytics.

    decision:
        accepted, rejected, or accepted_with_warnings.

    rejection_reasons:
        Hard reasons why analytics must not count this event.

    warnings:
        Soft issues useful for debugging but not always rejection-worthy.
    """

    is_event_accepted: bool
    decision: str
    ml_confidence: float
    min_ml_confidence: float
    is_ml_confidence_accepted: bool
    image_captured: bool
    session_triggered: bool | None
    compartment_confirmed: bool | None
    metal_detected: bool | None
    metal_evidence_status: str
    rejection_reasons: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_optional_bool(value: bool | None, name: str) -> bool | None:
    """
    Validate optional boolean sensor inputs.
    """

    if value is None:
        return None

    if not isinstance(value, bool):
        raise ConfidenceEngineError(
            f"{name} must be True, False, or None. Got {type(value).__name__}"
        )

    return value


def _validate_confidence_value(value: float, name: str) -> float:
    """
    Validate confidence value.
    """

    if isinstance(value, bool):
        raise ConfidenceEngineError(f"{name} must be numeric, not boolean")

    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfidenceEngineError(f"{name} must be numeric, got {value!r}") from exc

    if normalized < 0.0 or normalized > 1.0:
        raise ConfidenceEngineError(
            f"{name} must be between 0.0 and 1.0, got {normalized}"
        )

    return normalized


def evaluate_metal_evidence(
    predicted_class: str,
    metal_detected: bool | None,
) -> tuple[str, list[str]]:
    """
    Evaluate Omron metal sensor evidence.

    Important:
        Metal sensor does not override ML.
        It only gives supporting or conflicting evidence.

    Returns:
        status, warnings
    """

    warnings: list[str] = []

    if metal_detected is None:
        return "not_available", warnings

    normalized_class = predicted_class.strip().lower()

    if metal_detected and normalized_class == "metal":
        return "supports_metal_prediction", warnings

    if metal_detected and normalized_class != "metal":
        warnings.append(
            "metal_sensor_detected_metal_but_ml_predicted_non_metal"
        )
        return "conflicts_with_ml_prediction", warnings

    if not metal_detected and normalized_class == "metal":
        warnings.append(
            "ml_predicted_metal_but_metal_sensor_did_not_confirm"
        )
        return "missing_expected_metal_confirmation", warnings

    return "supports_non_metal_prediction", warnings


def evaluate_event_confidence(
    validation_result: DisposalValidationResult,
    *,
    image_captured: bool = True,
    session_triggered: bool | None = None,
    compartment_confirmed: bool | None = None,
    metal_detected: bool | None = None,
    min_ml_confidence: float = MIN_CONFIDENCE,
    require_image_capture: bool = True,
    require_session_trigger: bool = False,
    require_compartment_confirmation: bool = False,
) -> ConfidenceDecision:
    """
    Evaluate whether a disposal event should be counted.

    Current acceptance rule:
        accepted only if ML confidence passes and all required evidence passes.

    Sensor-ready future behavior:
        When ultrasonic sensors are integrated, set:
            require_session_trigger=True
            require_compartment_confirmation=True
    """

    if not isinstance(validation_result, DisposalValidationResult):
        raise ConfidenceEngineError(
            "validation_result must be a DisposalValidationResult"
        )

    image_captured = _validate_optional_bool(image_captured, "image_captured")
    session_triggered = _validate_optional_bool(session_triggered, "session_triggered")
    compartment_confirmed = _validate_optional_bool(
        compartment_confirmed,
        "compartment_confirmed",
    )
    metal_detected = _validate_optional_bool(metal_detected, "metal_detected")

    min_confidence = _validate_confidence_value(
        min_ml_confidence,
        "min_ml_confidence",
    )

    ml_confidence = _validate_confidence_value(
        validation_result.confidence,
        "validation_result.confidence",
    )

    rejection_reasons: list[str] = []
    warnings: list[str] = []

    is_ml_confidence_accepted = ml_confidence >= min_confidence

    if not is_ml_confidence_accepted:
        rejection_reasons.append(
            f"low_ml_confidence:{ml_confidence:.3f}<min:{min_confidence:.3f}"
        )

    if require_image_capture and not image_captured:
        rejection_reasons.append("image_capture_missing")

    if require_session_trigger:
        if session_triggered is not True:
            rejection_reasons.append("session_trigger_missing")

    if require_compartment_confirmation:
        if compartment_confirmed is not True:
            rejection_reasons.append("compartment_confirmation_missing")

    metal_status, metal_warnings = evaluate_metal_evidence(
        predicted_class=validation_result.predicted_class,
        metal_detected=metal_detected,
    )
    warnings.extend(metal_warnings)

    if metal_status == "conflicts_with_ml_prediction":
        warnings.append("metal_sensor_conflict_requires_review")

    if metal_status == "missing_expected_metal_confirmation":
        warnings.append("metal_prediction_without_sensor_support")

    # Metal evidence is deliberately not used as a hard accept/reject rule yet.
    # This keeps the product rule intact: metal sensor is a confidence booster,
    # not the sole truth source.
    is_accepted = len(rejection_reasons) == 0

    if is_accepted and warnings:
        decision = "accepted_with_warnings"
    elif is_accepted:
        decision = "accepted"
    else:
        decision = "rejected"

    result = ConfidenceDecision(
        is_event_accepted=is_accepted,
        decision=decision,
        ml_confidence=ml_confidence,
        min_ml_confidence=min_confidence,
        is_ml_confidence_accepted=is_ml_confidence_accepted,
        image_captured=bool(image_captured),
        session_triggered=session_triggered,
        compartment_confirmed=compartment_confirmed,
        metal_detected=metal_detected,
        metal_evidence_status=metal_status,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
    )

    logger.info(
        "Confidence decision | accepted=%s | decision=%s | ml=%.3f | reasons=%s | warnings=%s",
        result.is_event_accepted,
        result.decision,
        result.ml_confidence,
        result.rejection_reasons,
        result.warnings,
    )

    return result


def evaluate_payload_confidence(
    payload: dict[str, Any],
    *,
    image_captured: bool = True,
    session_triggered: bool | None = None,
    compartment_confirmed: bool | None = None,
    metal_detected: bool | None = None,
    min_ml_confidence: float = MIN_CONFIDENCE,
    require_image_capture: bool = True,
    require_session_trigger: bool = False,
    require_compartment_confirmation: bool = False,
) -> ConfidenceDecision:
    """
    Evaluate confidence using an existing payload dictionary.

    This helper is useful after payload generation.
    """

    required_keys = [
        "predictedClass",
        "recyclability",
        "confidence",
        "disposalSide",
        "expectedSide",
        "isCorrectDisposal",
        "isConfidenceAccepted",
        "isEventAccepted",
        "rejectionReason",
    ]

    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise ConfidenceEngineError(
            f"Payload is missing required keys: {', '.join(missing)}"
        )

    validation_result = DisposalValidationResult(
        predicted_class=str(payload["predictedClass"]),
        recyclability=str(payload["recyclability"]),
        confidence=float(payload["confidence"]),
        disposal_side=str(payload["disposalSide"]),
        expected_side=str(payload["expectedSide"]),
        is_correct_disposal=bool(payload["isCorrectDisposal"]),
        is_confidence_accepted=bool(payload["isConfidenceAccepted"]),
        is_event_accepted=bool(payload["isEventAccepted"]),
        rejection_reason=payload["rejectionReason"],
    )

    return evaluate_event_confidence(
        validation_result,
        image_captured=image_captured,
        session_triggered=session_triggered,
        compartment_confirmed=compartment_confirmed,
        metal_detected=metal_detected,
        min_ml_confidence=min_ml_confidence,
        require_image_capture=require_image_capture,
        require_session_trigger=require_session_trigger,
        require_compartment_confirmation=require_compartment_confirmation,
    )


__all__ = [
    "ConfidenceEngineError",
    "ConfidenceDecision",
    "evaluate_metal_evidence",
    "evaluate_event_confidence",
    "evaluate_payload_confidence",
]
