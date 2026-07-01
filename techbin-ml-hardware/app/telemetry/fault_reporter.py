"""
Fault reporter for TechBin device runtime.

Purpose:
    Create, save, and optionally queue structured device fault payloads.

Fault examples:
    - camera_failure
    - inference_failure
    - sensor_failure
    - telemetry_failure
    - low_confidence_warning
    - runtime_exception
    - ultrasonic_echo_timeout
    - metal_sensor_signal_fault

Important:
    Fault reporting is separate from disposal analytics.
    A fault payload should help maintenance/debugging, not increase disposal counts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.logger import get_logger
from app.telemetry.payloads import PayloadBuildError, build_fault_payload
from app.telemetry.uploader import (
    TelemetryUploadError,
    TelemetryUploader,
    UploadResult,
)
from app.utils.event_logger import EventLogError, save_event_log


logger = get_logger(__name__)


FaultSeverity = Literal["info", "warning", "critical"]

FaultTelemetryMode = Literal[
    "none",
    "queue",
    "upload_or_queue",
]


class FaultReporterError(RuntimeError):
    """Raised when a fault report cannot be created/saved/queued."""


@dataclass(frozen=True)
class FaultReportResult:
    """
    Result returned after reporting one fault.
    """

    payload: dict[str, Any]
    log_path: str
    telemetry: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_fault_code(fault_code: str) -> str:
    """
    Normalize a fault code into a stable machine-readable value.
    """

    if not isinstance(fault_code, str) or fault_code.strip() == "":
        raise FaultReporterError("fault_code cannot be empty")

    normalized = fault_code.strip().lower()
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("-", "_")

    safe_chars = []
    for char in normalized:
        if char.isalnum() or char == "_":
            safe_chars.append(char)

    safe = "".join(safe_chars).strip("_")

    if safe == "":
        raise FaultReporterError("fault_code became empty after normalization")

    return safe


def _normalize_component(component: str) -> str:
    """
    Normalize hardware/software component name.
    """

    if not isinstance(component, str) or component.strip() == "":
        raise FaultReporterError("component cannot be empty")

    normalized = component.strip().lower()
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("-", "_")

    return normalized


def _normalize_message(message: str) -> str:
    """
    Validate and normalize human-readable fault message.
    """

    if not isinstance(message, str) or message.strip() == "":
        raise FaultReporterError("message cannot be empty")

    return message.strip()


def _normalize_severity(severity: str) -> FaultSeverity:
    """
    Validate severity.
    """

    if not isinstance(severity, str) or severity.strip() == "":
        raise FaultReporterError("severity cannot be empty")

    normalized = severity.strip().lower()

    if normalized not in ("info", "warning", "critical"):
        raise FaultReporterError("severity must be one of: info, warning, critical")

    return normalized  # type: ignore[return-value]


def _handle_fault_telemetry(
    payload: dict[str, Any],
    *,
    uploader: TelemetryUploader,
    telemetry_mode: FaultTelemetryMode,
    telemetry_prefix: str,
) -> UploadResult | None:
    """
    Queue or upload a fault payload.
    """

    if telemetry_mode == "none":
        logger.info("Fault telemetry skipped because telemetry_mode=none")
        return None

    if telemetry_mode == "queue":
        queue_path = uploader.enqueue(
            payload,
            prefix=telemetry_prefix,
        )

        return UploadResult(
            payload_id="queued",
            status="queued",
            message="fault_queued_for_later_upload",
            queue_path=str(queue_path),
            response_status_code=None,
            attempts=0,
        )

    if telemetry_mode == "upload_or_queue":
        return uploader.upload_or_queue(
            payload,
            prefix=telemetry_prefix,
        )

    raise FaultReporterError(f"Unsupported telemetry_mode: {telemetry_mode}")


@dataclass
class FaultReporter:
    """
    Production fault reporter.

    Default behavior:
        - always save local JSON fault log
        - queue fault telemetry locally
        - do not crash main runtime if telemetry queue fails unless configured
    """

    telemetry_uploader: TelemetryUploader | None = None
    source: str = "fault_reporter"
    log_prefix: str = "fault"
    telemetry_prefix: str = "fault"
    telemetry_mode: FaultTelemetryMode = "queue"
    fail_on_telemetry_error: bool = False

    def report_fault(
        self,
        fault_code: str,
        severity: FaultSeverity | str,
        message: str,
        component: str,
        *,
        is_resolved: bool = False,
    ) -> FaultReportResult:
        """
        Build, save, and optionally queue one fault payload.
        """

        try:
            normalized_fault_code = _normalize_fault_code(fault_code)
            normalized_component = _normalize_component(component)
            normalized_message = _normalize_message(message)
            normalized_severity = _normalize_severity(str(severity))

            payload = build_fault_payload(
                fault_code=normalized_fault_code,
                severity=normalized_severity,
                message=normalized_message,
                component=normalized_component,
                source=self.source,
                is_resolved=is_resolved,
            )

            log_path = save_event_log(
                payload,
                prefix=self.log_prefix,
            )

            telemetry_result: UploadResult | None = None

            try:
                uploader = self.telemetry_uploader or TelemetryUploader()

                telemetry_result = _handle_fault_telemetry(
                    payload,
                    uploader=uploader,
                    telemetry_mode=self.telemetry_mode,
                    telemetry_prefix=self.telemetry_prefix,
                )

            except TelemetryUploadError as exc:
                logger.error("Fault telemetry handling failed: %s", exc)

                if self.fail_on_telemetry_error:
                    raise

                telemetry_result = UploadResult(
                    payload_id="unknown",
                    status="failed",
                    message=f"fault_telemetry_error:{exc}",
                    queue_path=None,
                    response_status_code=None,
                    attempts=0,
                )

            logger.warning(
                "Fault reported | code=%s | severity=%s | component=%s | telemetry=%s | log=%s",
                payload["faultCode"],
                payload["severity"],
                payload["component"],
                telemetry_result.status if telemetry_result else "skipped",
                log_path,
            )

            return FaultReportResult(
                payload=payload,
                log_path=str(log_path),
                telemetry=(
                    telemetry_result.to_dict()
                    if telemetry_result is not None
                    else None
                ),
            )

        except (
            PayloadBuildError,
            EventLogError,
            TelemetryUploadError,
            FaultReporterError,
        ):
            raise

        except Exception as exc:
            raise FaultReporterError("Unexpected fault reporting failure") from exc


def report_fault(
    fault_code: str,
    severity: FaultSeverity | str,
    message: str,
    component: str,
    *,
    source: str = "fault_reporter",
    log_prefix: str = "fault",
    telemetry_prefix: str = "fault",
    telemetry_mode: FaultTelemetryMode = "queue",
    telemetry_uploader: TelemetryUploader | None = None,
    fail_on_telemetry_error: bool = False,
    is_resolved: bool = False,
) -> FaultReportResult:
    """
    Convenience function for one-off fault reporting.
    """

    reporter = FaultReporter(
        telemetry_uploader=telemetry_uploader,
        source=source,
        log_prefix=log_prefix,
        telemetry_prefix=telemetry_prefix,
        telemetry_mode=telemetry_mode,
        fail_on_telemetry_error=fail_on_telemetry_error,
    )

    return reporter.report_fault(
        fault_code=fault_code,
        severity=severity,
        message=message,
        component=component,
        is_resolved=is_resolved,
    )


__all__ = [
    "FaultSeverity",
    "FaultTelemetryMode",
    "FaultReporterError",
    "FaultReportResult",
    "FaultReporter",
    "report_fault",
]
