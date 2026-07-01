#!/usr/bin/env python3
"""
Safe single-sensor HC-SR04 test for TechBin.
Only one sensor is created and triggered per run.
"""

from __future__ import annotations

import statistics
import sys
import time

from gpiozero import DistanceSensor

SENSORS = {
    "left": {
        "trigger": 5,
        "echo": 6,
        "expected_empty_cm": 37.7,
    },
    "right": {
        "trigger": 16,
        "echo": 20,
        "expected_empty_cm": 38.9,
    },
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1].lower() not in SENSORS:
        print("Usage: python3 scripts/test_one_direct_hcsr04.py left")
        print("   or: python3 scripts/test_one_direct_hcsr04.py right")
        raise SystemExit(1)

    side = sys.argv[1].lower()
    cfg = SENSORS[side]

    print()
    print(f"Testing {side.upper()} HC-SR04")
    print(f"TRIG: GPIO{cfg['trigger']} | ECHO: GPIO{cfg['echo']}")
    print(f"Expected empty-bin distance: about {cfg['expected_empty_cm']} cm")
    print()

    sensor = DistanceSensor(
        trigger=cfg["trigger"],
        echo=cfg["echo"],
        max_distance=0.80,
        queue_len=1,
        partial=True,
    )

    readings = []

    try:
        time.sleep(1.5)

        for number in range(1, 11):
            distance_cm = sensor.distance * 100.0
            readings.append(distance_cm)

            print(f"Reading {number:02d}: {distance_cm:6.2f} cm")
            time.sleep(0.5)

    finally:
        sensor.close()

    print()

    valid = [value for value in readings if 2.0 <= value < 79.0]

    if not valid:
        print("RESULT: No valid readings.")
        print("Check VCC, GND, Echo divider, Pi pin number, and breadboard rail connection.")
        return

    print(f"Median: {statistics.median(valid):.2f} cm")
    print(f"Range:  {min(valid):.2f} to {max(valid):.2f} cm")

    if len(valid) < 7:
        print("RESULT: Sensor is partly responding but readings are unstable.")
    else:
        print("RESULT: Sensor is responding. Compare the median with expected empty-bin distance.")


if __name__ == "__main__":
    main()
