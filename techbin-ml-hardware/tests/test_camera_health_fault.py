"""
Test camera health check and fault reporting.

This test is safe to run whether the camera is connected or not.

If camera is connected:
    health check should pass and no fault is reported.

If camera is not connected:
    health check should fail cleanly and a structured camera fault is saved/queued.

Run:
    PYTHONPATH=. python3 tests/test_camera_health_fault.py
"""

from __future__ import annotations

from pathlib import Path
from pprint import pprint

from app.sensors.health_check import DeviceHealthChecker


def main() -> None:
    checker = DeviceHealthChecker()

    result = checker.check_camera_available()

    print()
    print("========== Camera Health Result ==========")
    pprint(result.to_dict())

    if result.ok:
        print()
        print("Camera is healthy. No fault report needed.")
        print("PASS: camera health check")
        return

    fault_result = checker.report_fault_if_unhealthy(result)

    print()
    print("========== Camera Fault Report ==========")
    pprint(fault_result.to_dict())

    assert fault_result is not None
    assert fault_result.payload["faultCode"] == result.fault_code
    assert fault_result.payload["component"] == "camera"
    assert fault_result.payload["severity"] in ("warning", "critical")
    assert Path(fault_result.log_path).exists()
    assert fault_result.telemetry is not None
    assert fault_result.telemetry["status"] == "queued"

    print()
    print("PASS: camera missing was converted into structured fault")


if __name__ == "__main__":
    main()
