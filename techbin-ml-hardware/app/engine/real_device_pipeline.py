"""
Permanent real-device TechBin disposal pipeline.

Flow:
    front-session trigger
    -> capture side baseline
    -> wait for item positioning
    -> real camera/model prediction
    -> confidence/margin validation
    -> confirm actual ultrasonic side
    -> refresh capacity/lights
    -> save local confirmed event
    -> update totals
    -> send Supabase payload through existing queue/retry
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.config import settings
from app.logger import get_logger
from app.ml.effnetv2 import EfficientNetV2CameraClassifier, RealPredictionResult
from app.sensors.direct_pi_stack import DirectPiHardwareStack, build_direct_pi_hardware_stack
from app.telemetry.supabase import (
    build_bin_state_payload,
    build_faults_payload,
    build_latest_event,
    build_supabase_transport,
    extract_capacity_sensor_payload,
    new_event_id,
    physical_side_to_supabase,
)
from app.telemetry.totals import LocalTotalsStore
from app.telemetry.uploader import TelemetryUploader, UploadResult
from app.utils.event_logger import save_event_log


logger = get_logger(__name__)


TelemetryMode = Literal["none", "queue", "upload_or_queue"]
RealPipelineStatus = Literal[
    "processed",
    "uncertain_prediction",
    "side_unconfirmed",
    "fault",
]


class RealDevicePipelineError(RuntimeError):
    """Raised when real-device pipeline setup fails."""


@dataclass(frozen=True)
class RealDevicePipelineConfig:
    front_poll_seconds: float = 0.45
    item_position_seconds: float = 2.5
    side_confirm_timeout_seconds: float = 12.0
    side_poll_seconds: float = 0.45
    telemetry_mode: TelemetryMode = "upload_or_queue"
    source: str = "real_device_pipeline"
    log_prefix: str = "supabase_event"
    telemetry_prefix: str = "supabase_event"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealDevicePipelineResult:
    timestamp: str
    status: RealPipelineStatus
    processed: bool
    message: str
    eventId: str | None
    prediction: dict[str, Any] | None
    sideDetection: dict[str, Any] | None
    capacity: dict[str, Any] | None
    totals: dict[str, int] | None
    supabasePayload: dict[str, Any] | None
    logPath: str | None
    telemetry: dict[str, Any] | None
    faultCode: str | None
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="microseconds")


def _to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _build_camera():
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        raise RealDevicePipelineError(
            "picamera2 is required for real-device runtime"
        ) from exc

    camera = Picamera2()
    camera_config = camera.create_preview_configuration(
        main={"size": (720, 720), "format": "RGB888"}
    )
    camera.configure(camera_config)
    camera.start()
    time.sleep(1.5)
    return camera


class RealDeviceDisposalPipeline:
    """
    Runs one real hardware disposal session.
    """

    def __init__(
        self,
        *,
        hardware_stack: DirectPiHardwareStack | Any | None = None,
        classifier: EfficientNetV2CameraClassifier | Any | None = None,
        totals_store: LocalTotalsStore | None = None,
        telemetry_uploader: TelemetryUploader | None = None,
        config: RealDevicePipelineConfig | None = None,
    ) -> None:
        self.hardware_stack = hardware_stack
        self.classifier = classifier
        self.totals_store = totals_store or LocalTotalsStore()
        self.telemetry_uploader = telemetry_uploader
        self.config = config or RealDevicePipelineConfig()

    def _get_hardware_stack(self):
        if self.hardware_stack is None:
            self.hardware_stack = build_direct_pi_hardware_stack()

        return self.hardware_stack

    def _get_classifier(self):
        if self.classifier is None:
            self.classifier = EfficientNetV2CameraClassifier()

        return self.classifier

    def _get_uploader(self) -> TelemetryUploader:
        if self.telemetry_uploader is None:
            self.telemetry_uploader = TelemetryUploader(
                transport=build_supabase_transport()
            )

        return self.telemetry_uploader

    def _wait_for_front_session(self, stack: Any) -> dict[str, Any]:
        while True:
            session_result = stack.session_detector.update()
            session_data = session_result.to_dict()

            if session_data.get("sessionStarted") or session_data.get("sessionActive"):
                return session_data

            time.sleep(self.config.front_poll_seconds)

    def _confirm_side(self, stack: Any) -> Any | None:
        deadline = time.monotonic() + self.config.side_confirm_timeout_seconds

        last_result = None
        while time.monotonic() < deadline:
            side_result = stack.side_detector.detect_once()
            last_result = side_result
            side_data = side_result.to_dict()

            if side_data.get("valid") and side_data.get("disposalSide") in (
                "left",
                "right",
            ):
                return side_result

            time.sleep(self.config.side_poll_seconds)

        return last_result

    def _handle_telemetry(
        self,
        payload: dict[str, Any],
        *,
        event_id: str,
    ) -> UploadResult | None:
        if self.config.telemetry_mode == "none":
            return None

        uploader = self._get_uploader()

        if self.config.telemetry_mode == "queue":
            queue_path = uploader.enqueue(
                payload,
                prefix=self.config.telemetry_prefix,
                payload_id=event_id,
            )

            return UploadResult(
                payload_id=event_id,
                status="queued",
                message="queued_for_later_upload",
                queue_path=str(queue_path),
                response_status_code=None,
                attempts=0,
            )

        if self.config.telemetry_mode == "upload_or_queue":
            return uploader.upload_or_queue(
                payload,
                prefix=self.config.telemetry_prefix,
                payload_id=event_id,
            )

        raise RealDevicePipelineError(
            f"Unsupported telemetry_mode: {self.config.telemetry_mode}"
        )

    def process_once(self, camera: Any | None = None) -> RealDevicePipelineResult:
        stack = None
        owns_camera = camera is None
        active_camera = camera
        prediction: RealPredictionResult | None = None
        side_result = None
        capacity_result = None

        try:
            stack = self._get_hardware_stack()
            classifier = self._get_classifier()

            self._wait_for_front_session(stack)
            stack.side_detector.capture_baseline()

            if self.config.item_position_seconds > 0:
                time.sleep(self.config.item_position_seconds)

            if active_camera is None:
                active_camera = _build_camera()

            prediction = classifier.capture_average_prediction(active_camera)

            if not prediction.accepted:
                return RealDevicePipelineResult(
                    timestamp=_now_iso(),
                    status="uncertain_prediction",
                    processed=False,
                    message=prediction.rejectionReason or "prediction_rejected",
                    eventId=None,
                    prediction=prediction.to_dict(),
                    sideDetection=None,
                    capacity=None,
                    totals=None,
                    supabasePayload=None,
                    logPath=None,
                    telemetry=None,
                    faultCode="uncertain_prediction",
                    config=self.config.to_dict(),
                )

            side_result = self._confirm_side(stack)
            side_data = _to_dict(side_result)

            if (
                side_data is None
                or not side_data.get("valid")
                or side_data.get("disposalSide") not in ("left", "right")
            ):
                return RealDevicePipelineResult(
                    timestamp=_now_iso(),
                    status="side_unconfirmed",
                    processed=False,
                    message="Physical disposal side was not confirmed.",
                    eventId=None,
                    prediction=prediction.to_dict(),
                    sideDetection=side_data,
                    capacity=None,
                    totals=None,
                    supabasePayload=None,
                    logPath=None,
                    telemetry=None,
                    faultCode="side_unconfirmed",
                    config=self.config.to_dict(),
                )

            capacity_result = stack.capacity_monitor.check_all()
            capacity_data = _to_dict(capacity_result)
            sensor_payload = extract_capacity_sensor_payload(capacity_data)

            event_id = new_event_id(settings.supabase.bin_code)
            disposed_side = physical_side_to_supabase(str(side_data["disposalSide"]))

            latest_event = build_latest_event(
                event_id=event_id,
                category=prediction.category,
                disposed_side=disposed_side,
                confidence=prediction.confidence,
                model_version=prediction.modelVersion,
                classification_source=prediction.classificationSource,
                label=prediction.label,
                placement_confirmed=True,
                image_url=None,
            )

            totals = self.totals_store.update_for_confirmed_event(
                category=prediction.category,
                correct=bool(latest_event["correct"]),
            )

            ultrasonic_fault = False
            if isinstance(capacity_data, dict):
                ultrasonic_fault = not bool(capacity_data.get("overallValid", True))

            payload = build_bin_state_payload(
                statistics=totals,
                sensors=sensor_payload,
                faults=build_faults_payload(ultrasonic=ultrasonic_fault),
                latest_event=latest_event,
                status_state="normal",
                status_message="Running",
            )

            log_path = save_event_log(
                payload,
                prefix=self.config.log_prefix,
            )

            telemetry_result = self._handle_telemetry(payload, event_id=event_id)

            return RealDevicePipelineResult(
                timestamp=_now_iso(),
                status="processed",
                processed=True,
                message="Confirmed disposal event processed.",
                eventId=event_id,
                prediction=prediction.to_dict(),
                sideDetection=side_data,
                capacity=capacity_data,
                totals=totals,
                supabasePayload=payload,
                logPath=str(log_path),
                telemetry=(
                    telemetry_result.to_dict()
                    if telemetry_result is not None
                    else None
                ),
                faultCode=None,
                config=self.config.to_dict(),
            )

        except Exception as exc:
            logger.exception("Real-device pipeline failed")
            return RealDevicePipelineResult(
                timestamp=_now_iso(),
                status="fault",
                processed=False,
                message=str(exc),
                eventId=None,
                prediction=prediction.to_dict() if prediction is not None else None,
                sideDetection=_to_dict(side_result),
                capacity=_to_dict(capacity_result),
                totals=None,
                supabasePayload=None,
                logPath=None,
                telemetry=None,
                faultCode="real_device_pipeline_failed",
                config=self.config.to_dict(),
            )

        finally:
            if owns_camera and active_camera is not None:
                try:
                    active_camera.stop()
                except Exception:
                    pass
                try:
                    active_camera.close()
                except Exception:
                    pass


__all__ = [
    "TelemetryMode",
    "RealPipelineStatus",
    "RealDevicePipelineError",
    "RealDevicePipelineConfig",
    "RealDevicePipelineResult",
    "RealDeviceDisposalPipeline",
]
