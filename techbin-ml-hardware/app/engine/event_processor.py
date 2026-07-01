"""
Central disposal event processor for TechBin.

This module is the production entry point for one disposal event.

Current production foundation:
    - camera capture is supported
    - existing image path is supported
    - mock ML classifier is supported through a replaceable interface
    - disposal side is manual until sensors are integrated
    - confidence engine is integrated
    - local JSON event logging is integrated
    - telemetry queue is integrated

Future integrations:
    - real TFLite classifier
    - front ultrasonic user/session trigger
    - left/right compartment confirmation sensors
    - Omron metal sensor evidence
    - backend/Firebase telemetry uploader
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from app.camera.capture import CameraCaptureError, CaptureResult, capture_image
from app.config import settings
from app.engine.confidence_engine import (
    ConfidenceEngineError,
    evaluate_payload_confidence,
)
from app.engine.disposal_validator import (
    DisposalValidationError,
    normalize_disposal_side,
)
from app.logger import get_logger
from app.ml.infer import (
    InferenceError,
    InferenceResult,
    WasteClassifier,
    predict_image,
)
from app.telemetry.payloads import PayloadBuildError, build_disposal_event_payload
from app.telemetry.uploader import (
    TelemetryUploadError,
    TelemetryUploader,
    UploadResult,
)
from app.utils.event_logger import EventLogError, save_event_log


logger = get_logger(__name__)


TelemetryMode = Literal[
    "none",
    "queue",
    "upload_or_queue",
]

TelemetryPolicy = Literal[
    "accepted_only",
    "all_events",
]


class EventProcessingError(RuntimeError):
    """Raised when a disposal event cannot be processed."""


@dataclass(frozen=True)
class EventProcessingResult:
    """
    Complete result of one processed disposal event.

    Attributes:
        payload:
            Final validated telemetry/event payload.

        log_path:
            Local JSON event log path.

        image_path:
            Image used for inference.

        inference:
            ML inference result dictionary.

        telemetry:
            Telemetry queue/upload result dictionary, or None if disabled/skipped.

        was_captured_now:
            True when this processor captured a fresh image.

        source:
            Runtime source name.
    """

    payload: dict[str, Any]
    log_path: str
    image_path: str
    inference: dict[str, Any]
    telemetry: dict[str, Any] | None
    was_captured_now: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_existing_image_path(image_path: str | Path) -> Path:
    """
    Normalize and validate an existing image path.
    """

    if isinstance(image_path, Path):
        path = image_path.expanduser().resolve()

    elif isinstance(image_path, str):
        if image_path.strip() == "":
            raise EventProcessingError("image_path cannot be empty")

        path = Path(image_path).expanduser().resolve()

    else:
        raise EventProcessingError(
            f"image_path must be str or Path, got {type(image_path).__name__}"
        )

    if not path.exists():
        raise EventProcessingError(f"Image file does not exist: {path}")

    if not path.is_file():
        raise EventProcessingError(f"Image path is not a file: {path}")

    if path.stat().st_size <= 0:
        raise EventProcessingError(f"Image file is empty: {path}")

    return path


def _resolve_image_for_event(
    image_path: str | Path | None,
    capture_prefix: str,
) -> tuple[Path, bool]:
    """
    Return image path and whether it was captured now.

    If image_path is provided, use that existing image.
    If image_path is None, capture a fresh image from the camera.
    """

    if image_path is not None:
        return _normalize_existing_image_path(image_path), False

    capture_result: CaptureResult = capture_image(prefix=capture_prefix)
    return capture_result.image_path, True


def _apply_confidence_decision_to_payload(
    payload: dict[str, Any],
    confidence_decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Add confidence-engine fields to payload and calculate final acceptance.

    Final event acceptance:
        validator accepted AND confidence engine accepted
    """

    validator_accepted = bool(payload.get("isEventAccepted", False))
    confidence_engine_accepted = bool(
        confidence_decision.get("is_event_accepted", False)
    )

    final_accepted = validator_accepted and confidence_engine_accepted

    payload["validatorAccepted"] = validator_accepted
    payload["confidenceEngineAccepted"] = confidence_engine_accepted
    payload["isEventAccepted"] = final_accepted

    payload["confidenceDecision"] = confidence_decision.get("decision")
    payload["confidenceRejectionReasons"] = confidence_decision.get(
        "rejection_reasons",
        [],
    )
    payload["confidenceWarnings"] = confidence_decision.get("warnings", [])
    payload["metalEvidenceStatus"] = confidence_decision.get(
        "metal_evidence_status",
        "not_available",
    )

    if not final_accepted:
        existing_reason = payload.get("rejectionReason")
        confidence_reasons = payload["confidenceRejectionReasons"]

        if existing_reason and confidence_reasons:
            payload["rejectionReason"] = (
                f"{existing_reason}; confidence_engine: {confidence_reasons}"
            )
        elif confidence_reasons:
            payload["rejectionReason"] = f"confidence_engine: {confidence_reasons}"
        elif existing_reason:
            payload["rejectionReason"] = existing_reason
        else:
            payload["rejectionReason"] = "event_rejected"

    return payload


def _should_handle_telemetry(
    payload: dict[str, Any],
    telemetry_mode: TelemetryMode,
    telemetry_policy: TelemetryPolicy,
) -> bool:
    """
    Decide whether telemetry should be queued/uploaded.

    accepted_only:
        Only accepted analytics-worthy events are queued.

    all_events:
        Queue all events, including rejected/low-confidence events.
        Useful for debugging, but not recommended for final analytics ingestion.
    """

    if telemetry_mode == "none":
        return False

    if telemetry_policy == "all_events":
        return True

    if telemetry_policy == "accepted_only":
        return bool(payload.get("isEventAccepted", False))

    raise EventProcessingError(f"Unsupported telemetry_policy: {telemetry_policy}")


def _handle_telemetry(
    payload: dict[str, Any],
    *,
    telemetry_uploader: TelemetryUploader,
    telemetry_mode: TelemetryMode,
    telemetry_policy: TelemetryPolicy,
    telemetry_prefix: str,
) -> UploadResult | None:
    """
    Queue or upload telemetry depending on configured mode.
    """

    if not _should_handle_telemetry(
        payload=payload,
        telemetry_mode=telemetry_mode,
        telemetry_policy=telemetry_policy,
    ):
        logger.info(
            "Telemetry skipped | mode=%s | policy=%s | accepted=%s",
            telemetry_mode,
            telemetry_policy,
            payload.get("isEventAccepted"),
        )
        return None

    if telemetry_mode == "queue":
        queue_path = telemetry_uploader.enqueue(
            payload,
            prefix=telemetry_prefix,
        )

        return UploadResult(
            payload_id="queued",
            status="queued",
            message="queued_for_later_upload",
            queue_path=str(queue_path),
            response_status_code=None,
            attempts=0,
        )

    if telemetry_mode == "upload_or_queue":
        return telemetry_uploader.upload_or_queue(
            payload,
            prefix=telemetry_prefix,
        )

    if telemetry_mode == "none":
        return None

    raise EventProcessingError(f"Unsupported telemetry_mode: {telemetry_mode}")


@dataclass
class EventProcessor:
    """
    Central TechBin event processor.

    The classifier and telemetry uploader are injectable so production runtime
    can use:
        - mock classifier now
        - real TFLite classifier later
        - dry-run/local queue telemetry now
        - real backend/Firebase uploader later
    """

    classifier: WasteClassifier | None = None
    telemetry_uploader: TelemetryUploader | None = None
    source: str = "event_processor"
    capture_prefix: str = "event"
    log_prefix: str = "event"
    telemetry_prefix: str = "event"
    telemetry_mode: TelemetryMode = "queue"
    telemetry_policy: TelemetryPolicy = "accepted_only"
    fail_on_telemetry_error: bool = False

    def process_disposal_event(
        self,
        disposal_side: str,
        image_path: str | Path | None = None,
        min_confidence: float | None = None,
        session_triggered: bool | None = None,
        compartment_confirmed: bool | None = None,
        metal_detected: bool | None = None,
        require_session_trigger: bool = False,
        require_compartment_confirmation: bool = False,
    ) -> EventProcessingResult:
        """
        Process one disposal event.

        Current:
            disposal_side is manual.

        Later:
            disposal_side, session_triggered, compartment_confirmed, and
            metal_detected will come from real sensors.
        """

        try:
            normalized_side = normalize_disposal_side(disposal_side)

            resolved_image_path, was_captured_now = _resolve_image_for_event(
                image_path=image_path,
                capture_prefix=self.capture_prefix,
            )

            inference_result: InferenceResult = predict_image(
                resolved_image_path,
                classifier=self.classifier,
            )

            active_min_confidence = (
                settings.ml.min_confidence
                if min_confidence is None
                else min_confidence
            )

            payload = build_disposal_event_payload(
                predicted_class=inference_result.predicted_class,
                confidence=inference_result.confidence,
                image_path=resolved_image_path,
                disposal_side=normalized_side,
                source=self.source,
                min_confidence=active_min_confidence,
            )

            payload["modelName"] = inference_result.model_name
            payload["inferenceTimeMs"] = inference_result.inference_time_ms

            confidence_decision = evaluate_payload_confidence(
                payload,
                image_captured=True,
                session_triggered=session_triggered,
                compartment_confirmed=compartment_confirmed,
                metal_detected=metal_detected,
                min_ml_confidence=active_min_confidence,
                require_image_capture=True,
                require_session_trigger=require_session_trigger,
                require_compartment_confirmation=require_compartment_confirmation,
            )

            payload = _apply_confidence_decision_to_payload(
                payload=payload,
                confidence_decision=confidence_decision.to_dict(),
            )

            saved_path = save_event_log(
                payload,
                prefix=self.log_prefix,
            )

            telemetry_result: UploadResult | None = None

            try:
                uploader = self.telemetry_uploader or TelemetryUploader()

                telemetry_result = _handle_telemetry(
                    payload,
                    telemetry_uploader=uploader,
                    telemetry_mode=self.telemetry_mode,
                    telemetry_policy=self.telemetry_policy,
                    telemetry_prefix=self.telemetry_prefix,
                )

            except TelemetryUploadError as exc:
                logger.error("Telemetry handling failed: %s", exc)

                if self.fail_on_telemetry_error:
                    raise

                telemetry_result = UploadResult(
                    payload_id="unknown",
                    status="failed",
                    message=f"telemetry_error:{exc}",
                    queue_path=None,
                    response_status_code=None,
                    attempts=0,
                )

            logger.info(
                "Event processed | class=%s | confidence=%.3f | side=%s | expected=%s | correct=%s | accepted=%s | decision=%s | telemetry=%s | log=%s",
                payload["predictedClass"],
                payload["confidence"],
                payload["disposalSide"],
                payload["expectedSide"],
                payload["isCorrectDisposal"],
                payload["isEventAccepted"],
                payload["confidenceDecision"],
                telemetry_result.status if telemetry_result else "skipped",
                saved_path,
            )

            return EventProcessingResult(
                payload=payload,
                log_path=str(saved_path),
                image_path=str(resolved_image_path),
                inference=inference_result.to_dict(),
                telemetry=(
                    telemetry_result.to_dict()
                    if telemetry_result is not None
                    else None
                ),
                was_captured_now=was_captured_now,
                source=self.source,
            )

        except (
            CameraCaptureError,
            ConfidenceEngineError,
            DisposalValidationError,
            InferenceError,
            PayloadBuildError,
            EventLogError,
            TelemetryUploadError,
            EventProcessingError,
        ):
            raise

        except Exception as exc:
            raise EventProcessingError("Unexpected event processing failure") from exc


def process_disposal_event(
    disposal_side: str,
    image_path: str | Path | None = None,
    classifier: WasteClassifier | None = None,
    telemetry_uploader: TelemetryUploader | None = None,
    source: str = "event_processor",
    capture_prefix: str = "event",
    log_prefix: str = "event",
    telemetry_prefix: str = "event",
    telemetry_mode: TelemetryMode = "queue",
    telemetry_policy: TelemetryPolicy = "accepted_only",
    fail_on_telemetry_error: bool = False,
    min_confidence: float | None = None,
    session_triggered: bool | None = None,
    compartment_confirmed: bool | None = None,
    metal_detected: bool | None = None,
    require_session_trigger: bool = False,
    require_compartment_confirmation: bool = False,
) -> EventProcessingResult:
    """
    Convenience function for one-off event processing.
    """

    processor = EventProcessor(
        classifier=classifier,
        telemetry_uploader=telemetry_uploader,
        source=source,
        capture_prefix=capture_prefix,
        log_prefix=log_prefix,
        telemetry_prefix=telemetry_prefix,
        telemetry_mode=telemetry_mode,
        telemetry_policy=telemetry_policy,
        fail_on_telemetry_error=fail_on_telemetry_error,
    )

    return processor.process_disposal_event(
        disposal_side=disposal_side,
        image_path=image_path,
        min_confidence=min_confidence,
        session_triggered=session_triggered,
        compartment_confirmed=compartment_confirmed,
        metal_detected=metal_detected,
        require_session_trigger=require_session_trigger,
        require_compartment_confirmation=require_compartment_confirmation,
    )


__all__ = [
    "TelemetryMode",
    "TelemetryPolicy",
    "EventProcessingError",
    "EventProcessingResult",
    "EventProcessor",
    "process_disposal_event",
]
