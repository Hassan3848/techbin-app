"""
Test TechBin fault reporter.

This test saves local fault JSON logs and queues fault telemetry locally.

Run from project root:
    PYTHONPATH=. python3 tests/test_fault_reporter.py
"""

from __future__ import annotations

import shutil
from pathlib import Path
from pprint import pprint

from app.telemetry.fault_reporter import FaultReporter, report_fault
from app.telemetry.uploader import DryRunTransport, TelemetryUploader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_QUEUE_ROOT = PROJECT_ROOT / "logs" / "fault_queue_test"


def reset_test_queue() -> None:
    if TEST_QUEUE_ROOT.exists():
        shutil.rmtree(TEST_QUEUE_ROOT)


def test_one_off_fault() -> None:
    result = report_fault(
        fault_code="camera_failure",
        severity="critical",
        message="Camera failed to initialize during test.",
        component="camera",
        source="test_fault_reporter",
        log_prefix="test_fault",
        telemetry_prefix="test_fault",
        telemetry_mode="queue",
    )

    print()
    print("========== One-Off Fault ==========")
    pprint(result.to_dict())

    assert result.payload["eventType"] if "eventType" in result.payload else True
    assert result.payload["faultCode"] == "camera_failure"
    assert result.payload["severity"] == "critical"
    assert result.payload["component"] == "camera"
    assert Path(result.log_path).exists()
    assert result.telemetry is not None
    assert result.telemetry["status"] == "queued"

    print("PASS: one-off fault")


def test_fault_reporter_with_dry_run_upload_or_queue() -> None:
    reset_test_queue()

    uploader = TelemetryUploader(
        transport=DryRunTransport(),
        queue_root=TEST_QUEUE_ROOT,
        max_retries=3,
    )

    reporter = FaultReporter(
        telemetry_uploader=uploader,
        source="test_fault_reporter",
        log_prefix="test_fault",
        telemetry_prefix="test_fault",
        telemetry_mode="upload_or_queue",
    )

    result = reporter.report_fault(
        fault_code="inference_failure",
        severity="warning",
        message="Mock inference failure test.",
        component="ml_inference",
    )

    print()
    print("========== Fault Reporter Dry-Run Upload ==========")
    pprint(result.to_dict())

    assert result.payload["faultCode"] == "inference_failure"
    assert result.payload["severity"] == "warning"
    assert Path(result.log_path).exists()
    assert result.telemetry is not None
    assert result.telemetry["status"] == "sent"

    print("PASS: dry-run upload_or_queue fault")


def test_fault_without_telemetry() -> None:
    result = report_fault(
        fault_code="telemetry_disabled_test",
        severity="info",
        message="Testing fault logging without telemetry queue.",
        component="telemetry",
        source="test_fault_reporter",
        log_prefix="test_fault_no_telemetry",
        telemetry_mode="none",
    )

    print()
    print("========== Fault Without Telemetry ==========")
    pprint(result.to_dict())

    assert Path(result.log_path).exists()
    assert result.telemetry is None

    print("PASS: fault without telemetry")


def main() -> None:
    test_one_off_fault()
    test_fault_reporter_with_dry_run_upload_or_queue()
    test_fault_without_telemetry()

    print()
    print("All fault reporter tests passed.")


if __name__ == "__main__":
    main()
