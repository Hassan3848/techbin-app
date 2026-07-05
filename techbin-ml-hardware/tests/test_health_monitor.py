"""
Test TechBin production health monitor.

This test is safe whether camera is connected or not.

Run:
    PYTHONPATH=. python3 tests/test_health_monitor.py
"""

from __future__ import annotations

from pathlib import Path
from pprint import pprint

from app.sensors.health_check import DeviceHealthMonitor


def main() -> None:
    monitor = DeviceHealthMonitor(
        require_camera=True,
        require_model_file=False,
        require_ultrasonic=False,
        require_metal_sensor=False,
        require_audio=False,
    )

    summary = monitor.run_all_checks()

    print()
    print("========== TechBin Health Summary ==========")
    pprint(summary.to_dict())

    assert summary.total_checks >= 8
    assert summary.status in ("ok", "warning", "critical")
    assert summary.ok_count >= 1

    reports = monitor.report_all_faults(summary)

    print()
    print("========== Fault Reports Created ==========")

    for report in reports:
        pprint(report.to_dict())
        assert Path(report.log_path).exists()
        assert report.telemetry is not None

    print()
    print("Fault reports created:", len(reports))
    print("PASS: health monitor completed safely")


if __name__ == "__main__":
    main()
