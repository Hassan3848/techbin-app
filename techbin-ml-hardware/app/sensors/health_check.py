"""
Device health monitoring for TechBin.

Purpose:
    Detect runtime, hardware, model, telemetry, and future sensor health.

Current production behavior:
    - Checks runtime directories
    - Checks disk space
    - Checks Raspberry Pi camera command availability
    - Checks Raspberry Pi camera detection
    - Checks telemetry queue directories
    - Checks model directory / optional model file
    - Marks ultrasonic, metal sensor, and audio as not_configured until enabled

Important:
    Health monitoring is not ML.
    It is runtime fault detection based on real system evidence.

Statuses:
    ok              component is healthy
    warning         component has a non-fatal issue
    critical        component failure can break runtime
    not_configured  component is intentionally not enabled yet
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.config import ensure_runtime_directories, settings
from app.logger import get_logger
from app.telemetry.fault_reporter import FaultReporter, FaultReportResult


logger = get_logger(__name__)


class HealthCheckError(RuntimeError):
    """Raised when health monitoring fails unexpectedly."""


@dataclass(frozen=True)
class HealthCheckResult:
    """
    Result of one component health check.
    """

    component: str
    ok: bool
    status: str
    fault_code: str | None
    message: str
    checked_at: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthSummary:
    """
    Summary of all health checks.
    """

    overall_ok: bool
    status: str
    checked_at: str
    total_checks: int
    ok_count: int
    warning_count: int
    critical_count: int
    not_configured_count: int
    results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _result(
    *,
    component: str,
    ok: bool,
    status: str,
    fault_code: str | None,
    message: str,
    details: dict[str, Any] | None = None,
) -> HealthCheckResult:
    return HealthCheckResult(
        component=component,
        ok=ok,
        status=status,
        fault_code=fault_code,
        message=message,
        checked_at=_now_iso(),
        details=details or {},
    )


def _safe_command_output(value: str | None, max_chars: int = 4000) -> str:
    if value is None:
        return ""

    text = value.strip()

    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"

    return text


class DeviceHealthMonitor:
    """
    Production health monitor for TechBin.

    This class intentionally supports both current components and future
    hardware hooks. Future sensors can move from not_configured to real checks
    when wiring and GPIO configuration are finalized.
    """

    def __init__(
        self,
        *,
        require_camera: bool = True,
        require_model_file: bool = False,
        model_path: str | Path | None = None,
        require_ultrasonic: bool = False,
        require_metal_sensor: bool = False,
        require_audio: bool = False,
        min_free_disk_mb_warning: int = 500,
        min_free_disk_mb_critical: int = 100,
    ) -> None:
        self.require_camera = require_camera
        self.require_model_file = require_model_file
        self.model_path = Path(model_path).expanduser().resolve() if model_path else None
        self.require_ultrasonic = require_ultrasonic
        self.require_metal_sensor = require_metal_sensor
        self.require_audio = require_audio
        self.min_free_disk_mb_warning = min_free_disk_mb_warning
        self.min_free_disk_mb_critical = min_free_disk_mb_critical

    def check_runtime_directories(self) -> HealthCheckResult:
        """
        Check required runtime directories.
        """

        try:
            ensure_runtime_directories()

            required_dirs = [
                settings.project_root,
                settings.captures_dir,
                settings.logs_dir,
                settings.models_dir,
            ]

            missing_or_invalid = [
                str(path) for path in required_dirs if not path.exists() or not path.is_dir()
            ]

            if missing_or_invalid:
                return _result(
                    component="runtime_directories",
                    ok=False,
                    status="critical",
                    fault_code="runtime_directory_missing",
                    message="One or more runtime directories are missing or invalid.",
                    details={
                        "missing_or_invalid": missing_or_invalid,
                    },
                )

            return _result(
                component="runtime_directories",
                ok=True,
                status="ok",
                fault_code=None,
                message="Runtime directories are available.",
                details={
                    "project_root": str(settings.project_root),
                    "captures_dir": str(settings.captures_dir),
                    "logs_dir": str(settings.logs_dir),
                    "models_dir": str(settings.models_dir),
                },
            )

        except Exception as exc:
            return _result(
                component="runtime_directories",
                ok=False,
                status="critical",
                fault_code="runtime_directory_check_failed",
                message="Runtime directory check failed unexpectedly.",
                details={"error": str(exc)},
            )

    def check_disk_space(self) -> HealthCheckResult:
        """
        Check free disk space for logs, captures, and model files.
        """

        try:
            usage = shutil.disk_usage(settings.project_root)
            free_mb = int(usage.free / (1024 * 1024))
            total_mb = int(usage.total / (1024 * 1024))
            used_mb = int(usage.used / (1024 * 1024))

            details = {
                "project_root": str(settings.project_root),
                "total_mb": total_mb,
                "used_mb": used_mb,
                "free_mb": free_mb,
                "warning_threshold_mb": self.min_free_disk_mb_warning,
                "critical_threshold_mb": self.min_free_disk_mb_critical,
            }

            if free_mb < self.min_free_disk_mb_critical:
                return _result(
                    component="disk_space",
                    ok=False,
                    status="critical",
                    fault_code="disk_space_critical",
                    message="Free disk space is critically low.",
                    details=details,
                )

            if free_mb < self.min_free_disk_mb_warning:
                return _result(
                    component="disk_space",
                    ok=False,
                    status="warning",
                    fault_code="disk_space_low",
                    message="Free disk space is low.",
                    details=details,
                )

            return _result(
                component="disk_space",
                ok=True,
                status="ok",
                fault_code=None,
                message="Disk space is sufficient.",
                details=details,
            )

        except Exception as exc:
            return _result(
                component="disk_space",
                ok=False,
                status="critical",
                fault_code="disk_space_check_failed",
                message="Disk space check failed unexpectedly.",
                details={"error": str(exc)},
            )

    def check_camera_available(self, timeout_seconds: float = 8.0) -> HealthCheckResult:
        """
        Check whether Raspberry Pi camera is detected by rpicam.

        This check does not capture an image.
        """

        command_path = shutil.which("rpicam-hello")

        if command_path is None:
            status = "critical" if self.require_camera else "warning"

            return _result(
                component="camera",
                ok=False,
                status=status,
                fault_code="camera_command_missing",
                message="rpicam-hello command was not found.",
                details={
                    "command": "rpicam-hello --list-cameras",
                    "required": self.require_camera,
                },
            )

        command = [command_path, "--list-cameras"]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:
            return _result(
                component="camera",
                ok=False,
                status="critical" if self.require_camera else "warning",
                fault_code="camera_health_check_timeout",
                message="Camera health check timed out.",
                details={
                    "command": " ".join(command),
                    "timeout_seconds": timeout_seconds,
                    "required": self.require_camera,
                    "error": str(exc),
                },
            )

        except Exception as exc:
            return _result(
                component="camera",
                ok=False,
                status="critical" if self.require_camera else "warning",
                fault_code="camera_health_check_failed",
                message="Camera health check command failed unexpectedly.",
                details={
                    "command": " ".join(command),
                    "required": self.require_camera,
                    "error": str(exc),
                },
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        combined_output = f"{stdout}\n{stderr}".strip()
        combined_lower = combined_output.lower()

        no_camera_markers = (
            "no cameras available",
            "no camera available",
            "no cameras",
            "no camera",
            "cannot find camera",
            "available cameras",
        )

        # Some rpicam versions print a header even when no cameras are found.
        # So we check both return code and output content.
        likely_missing = (
            completed.returncode != 0
            or "no cameras" in combined_lower
            or "no camera" in combined_lower
            or "cannot find camera" in combined_lower
        )

        # If output contains a camera model/pipeline path, it is healthy.
        likely_detected = (
            "imx" in combined_lower
            or "/base/soc" in combined_lower
            or "available cameras" in combined_lower and ":" in combined_output
        )

        if likely_detected and not likely_missing:
            return _result(
                component="camera",
                ok=True,
                status="ok",
                fault_code=None,
                message="Raspberry Pi camera is detected.",
                details={
                    "command": " ".join(command),
                    "returncode": completed.returncode,
                    "stdout": _safe_command_output(stdout),
                    "stderr": _safe_command_output(stderr),
                    "required": self.require_camera,
                },
            )

        return _result(
            component="camera",
            ok=False,
            status="critical" if self.require_camera else "warning",
            fault_code="camera_not_detected",
            message="Raspberry Pi camera is not detected.",
            details={
                "command": " ".join(command),
                "returncode": completed.returncode,
                "stdout": _safe_command_output(stdout),
                "stderr": _safe_command_output(stderr),
                "required": self.require_camera,
            },
        )

    def check_model_files(self) -> HealthCheckResult:
        """
        Check model directory or specific configured model file.

        Current state:
            If no model is required yet, missing model file is not_configured.
        """

        try:
            settings.models_dir.mkdir(parents=True, exist_ok=True)

            if self.model_path is not None:
                if self.model_path.exists() and self.model_path.is_file():
                    return _result(
                        component="ml_model",
                        ok=True,
                        status="ok",
                        fault_code=None,
                        message="Configured model file exists.",
                        details={
                            "model_path": str(self.model_path),
                            "file_size_bytes": self.model_path.stat().st_size,
                            "required": self.require_model_file,
                        },
                    )

                return _result(
                    component="ml_model",
                    ok=False,
                    status="critical" if self.require_model_file else "not_configured",
                    fault_code=(
                        "model_file_missing"
                        if self.require_model_file
                        else None
                    ),
                    message=(
                        "Configured model file is missing."
                        if self.require_model_file
                        else "Model file is not configured yet."
                    ),
                    details={
                        "model_path": str(self.model_path),
                        "required": self.require_model_file,
                    },
                )

            model_files = sorted(
                list(settings.models_dir.glob("*.tflite"))
                + list(settings.models_dir.glob("*.keras"))
                + list(settings.models_dir.glob("*.h5"))
            )

            if model_files:
                return _result(
                    component="ml_model",
                    ok=True,
                    status="ok",
                    fault_code=None,
                    message="At least one model file exists.",
                    details={
                        "models_dir": str(settings.models_dir),
                        "model_files": [str(path) for path in model_files],
                        "required": self.require_model_file,
                    },
                )

            return _result(
                component="ml_model",
                ok=not self.require_model_file,
                status="critical" if self.require_model_file else "not_configured",
                fault_code="model_file_missing" if self.require_model_file else None,
                message=(
                    "No model file was found in models directory."
                    if self.require_model_file
                    else "Real ML model is not configured yet; mock inference is currently used."
                ),
                details={
                    "models_dir": str(settings.models_dir),
                    "accepted_extensions": [".tflite", ".keras", ".h5"],
                    "required": self.require_model_file,
                },
            )

        except Exception as exc:
            return _result(
                component="ml_model",
                ok=False,
                status="critical" if self.require_model_file else "warning",
                fault_code="model_file_check_failed",
                message="Model file check failed unexpectedly.",
                details={"error": str(exc)},
            )

    def check_telemetry_queue(self) -> HealthCheckResult:
        """
        Check telemetry queue directories.
        """

        try:
            queue_root = settings.logs_dir / "telemetry_queue"
            pending_dir = queue_root / "pending"
            sent_dir = queue_root / "sent"
            failed_dir = queue_root / "failed"

            for path in (pending_dir, sent_dir, failed_dir):
                path.mkdir(parents=True, exist_ok=True)

            invalid = [
                str(path)
                for path in (pending_dir, sent_dir, failed_dir)
                if not path.exists() or not path.is_dir()
            ]

            if invalid:
                return _result(
                    component="telemetry_queue",
                    ok=False,
                    status="critical",
                    fault_code="telemetry_queue_directory_missing",
                    message="Telemetry queue directories are missing or invalid.",
                    details={"invalid": invalid},
                )

            pending_count = len(list(pending_dir.glob("*.json")))
            failed_count = len(list(failed_dir.glob("*.json")))

            if failed_count > 0:
                return _result(
                    component="telemetry_queue",
                    ok=False,
                    status="warning",
                    fault_code="telemetry_failed_items_present",
                    message="Telemetry queue contains failed items.",
                    details={
                        "queue_root": str(queue_root),
                        "pending_count": pending_count,
                        "failed_count": failed_count,
                    },
                )

            return _result(
                component="telemetry_queue",
                ok=True,
                status="ok",
                fault_code=None,
                message="Telemetry queue directories are available.",
                details={
                    "queue_root": str(queue_root),
                    "pending_count": pending_count,
                    "failed_count": failed_count,
                },
            )

        except Exception as exc:
            return _result(
                component="telemetry_queue",
                ok=False,
                status="critical",
                fault_code="telemetry_queue_check_failed",
                message="Telemetry queue check failed unexpectedly.",
                details={"error": str(exc)},
            )

    def check_ultrasonic_status(self) -> HealthCheckResult:
        """
        Placeholder health check for ultrasonic sensors.

        We intentionally do not read GPIO until safe wiring and pin config exist.
        """

        if not self.require_ultrasonic:
            return _result(
                component="ultrasonic_sensors",
                ok=True,
                status="not_configured",
                fault_code=None,
                message="Ultrasonic sensors are not configured yet.",
                details={
                    "required": False,
                    "reason": "waiting_for_resistor_dividers_and_gpio_config",
                },
            )

        return _result(
            component="ultrasonic_sensors",
            ok=False,
            status="critical",
            fault_code="ultrasonic_not_integrated",
            message="Ultrasonic sensors are required but not integrated yet.",
            details={
                "required": True,
                "reason": "gpio_module_not_enabled_yet",
            },
        )

    def check_metal_sensor_status(self) -> HealthCheckResult:
        """
        Placeholder health check for Omron metal sensor.

        We intentionally do not read GPIO until isolation/interfacing is finalized.
        """

        if not self.require_metal_sensor:
            return _result(
                component="metal_sensor",
                ok=True,
                status="not_configured",
                fault_code=None,
                message="Metal sensor is not configured yet.",
                details={
                    "required": False,
                    "reason": "waiting_for_safe_interfacing_or_isolation",
                },
            )

        return _result(
            component="metal_sensor",
            ok=False,
            status="critical",
            fault_code="metal_sensor_not_integrated",
            message="Metal sensor is required but not integrated yet.",
            details={
                "required": True,
                "reason": "gpio_module_not_enabled_yet",
            },
        )

    def check_audio_status(self) -> HealthCheckResult:
        """
        Placeholder health check for speaker/audio.

        Audio is intentionally postponed.
        """

        if not self.require_audio:
            return _result(
                component="audio",
                ok=True,
                status="not_configured",
                fault_code=None,
                message="Audio module is postponed and not configured yet.",
                details={
                    "required": False,
                    "reason": "speaker_audio_phase_later",
                },
            )

        return _result(
            component="audio",
            ok=False,
            status="warning",
            fault_code="audio_not_integrated",
            message="Audio is required but not integrated yet.",
            details={
                "required": True,
                "reason": "audio_module_not_enabled_yet",
            },
        )

    def run_all_checks(self) -> HealthSummary:
        """
        Run all available health checks.
        """

        results = [
            self.check_runtime_directories(),
            self.check_disk_space(),
            self.check_camera_available(),
            self.check_model_files(),
            self.check_telemetry_queue(),
            self.check_ultrasonic_status(),
            self.check_metal_sensor_status(),
            self.check_audio_status(),
        ]

        return summarize_health(results)

    def report_fault_if_unhealthy(
        self,
        result: HealthCheckResult,
        reporter: FaultReporter | None = None,
    ) -> FaultReportResult | None:
        """
        Report a fault if result is warning or critical.

        ok and not_configured results do not create fault payloads unless they
        have a real fault_code.
        """

        if result.status in ("ok", "not_configured"):
            logger.info(
                "No fault report needed | component=%s | status=%s",
                result.component,
                result.status,
            )
            return None

        if result.fault_code is None:
            raise HealthCheckError(
                f"Unhealthy result for {result.component} has no fault_code"
            )

        active_reporter = reporter or FaultReporter(
            source="device_health_monitor",
            log_prefix="health_fault",
            telemetry_prefix="health_fault",
            telemetry_mode="queue",
        )

        logger.warning(
            "Reporting health fault | component=%s | status=%s | fault=%s",
            result.component,
            result.status,
            result.fault_code,
        )

        return active_reporter.report_fault(
            fault_code=result.fault_code,
            severity=result.status,
            message=result.message,
            component=result.component,
        )

    def report_all_faults(
        self,
        summary: HealthSummary,
        reporter: FaultReporter | None = None,
    ) -> list[FaultReportResult]:
        """
        Report faults for all warning/critical health results.
        """

        reports: list[FaultReportResult] = []

        for result_dict in summary.results:
            result = HealthCheckResult(
                component=str(result_dict["component"]),
                ok=bool(result_dict["ok"]),
                status=str(result_dict["status"]),
                fault_code=result_dict["fault_code"],
                message=str(result_dict["message"]),
                checked_at=str(result_dict["checked_at"]),
                details=dict(result_dict["details"]),
            )

            fault_report = self.report_fault_if_unhealthy(
                result,
                reporter=reporter,
            )

            if fault_report is not None:
                reports.append(fault_report)

        return reports


def summarize_health(results: Iterable[HealthCheckResult]) -> HealthSummary:
    """
    Build overall health summary.
    """

    result_list = list(results)

    critical_count = sum(1 for item in result_list if item.status == "critical")
    warning_count = sum(1 for item in result_list if item.status == "warning")
    not_configured_count = sum(1 for item in result_list if item.status == "not_configured")
    ok_count = sum(1 for item in result_list if item.status == "ok")

    overall_ok = critical_count == 0

    if critical_count > 0:
        status = "critical"
    elif warning_count > 0:
        status = "warning"
    else:
        status = "ok"

    return HealthSummary(
        overall_ok=overall_ok,
        status=status,
        checked_at=_now_iso(),
        total_checks=len(result_list),
        ok_count=ok_count,
        warning_count=warning_count,
        critical_count=critical_count,
        not_configured_count=not_configured_count,
        results=[item.to_dict() for item in result_list],
    )


def check_camera_health() -> HealthCheckResult:
    """
    Convenience function for camera health check.
    """

    monitor = DeviceHealthMonitor()
    return monitor.check_camera_available()


def run_health_monitor() -> HealthSummary:
    """
    Convenience function for all health checks.
    """

    monitor = DeviceHealthMonitor()
    return monitor.run_all_checks()


# Backward compatibility with earlier camera health test name.
DeviceHealthChecker = DeviceHealthMonitor


__all__ = [
    "HealthCheckError",
    "HealthCheckResult",
    "HealthSummary",
    "DeviceHealthMonitor",
    "DeviceHealthChecker",
    "summarize_health",
    "check_camera_health",
    "run_health_monitor",
]
