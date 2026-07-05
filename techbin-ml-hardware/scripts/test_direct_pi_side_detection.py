#!/usr/bin/env python3
"""
TechBin direct-Pi left/right side-detection hardware test.

Run:
    python3 scripts/test_direct_pi_side_detection.py left
    python3 scripts/test_direct_pi_side_detection.py right
"""

from __future__ import annotations

import statistics
import sys
import time

from gpiozero import DistanceSensor


SENSORS = {
    "left": {"trigger": 5, "echo": 6},
    "right": {"trigger": 16, "echo": 20},
}

THRESHOLD_CM = 4.0
DOMINANCE_MARGIN_CM = 2.0


def median_distance_cm(side: str, sample_count: int = 7) -> float:
    cfg = SENSORS[side]
    sensor = DistanceSensor(
        trigger=cfg["trigger"],
        echo=cfg["echo"],
        max_distance=0.80,
        queue_len=1,
        partial=True,
    )

    values: list[float] = []

    try:
        time.sleep(0.8)

        for _ in range(sample_count):
            value = sensor.distance * 100.0

            if 2.0 <= value < 79.5:
                values.append(value)

            time.sleep(0.20)

    finally:
        sensor.close()

    if len(values) < 5:
        raise RuntimeError(
            f"{side} sensor did not provide enough valid readings: {values}"
        )

    return statistics.median(values)


def read_pair() -> tuple[float, float]:
    left = median_distance_cm("left")

    # Prevent leftover left echo from affecting the right reading.
    time.sleep(0.35)

    right = median_distance_cm("right")

    return left, right


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1].lower() not in {"left", "right"}:
        print("Usage:")
        print("  python3 scripts/test_direct_pi_side_detection.py left")
        print("  python3 scripts/test_direct_pi_side_detection.py right")
        raise SystemExit(1)

    expected_side = sys.argv[1].lower()

    print()
    print("=== TechBin Direct-Pi Disposal-Side Detection Test ===")
    print(f"Expected disturbed side: {expected_side.upper()}")
    print()
    print("Keep BOTH compartments empty for the baseline.")
    print("The script will capture baseline readings now.")
    print()

    baseline_left, baseline_right = read_pair()

    print(f"Baseline left : {baseline_left:.2f} cm")
    print(f"Baseline right: {baseline_right:.2f} cm")
    print()

    input(
        f"Place or HOLD a book/cardboard at least 10 cm below the "
        f"{expected_side.upper()} sensor, then press ENTER..."
    )

    print()
    print("Capturing after-object readings. Keep the object still.")
    print()

    after_left, after_right = read_pair()

    left_drop = baseline_left - after_left
    right_drop = baseline_right - after_right

    print(f"After left    : {after_left:.2f} cm")
    print(f"After right   : {after_right:.2f} cm")
    print()
    print(f"Left distance decrease : {left_drop:.2f} cm")
    print(f"Right distance decrease: {right_drop:.2f} cm")
    print()

    detected = "unknown"

    if (
        left_drop >= THRESHOLD_CM
        and left_drop >= right_drop + DOMINANCE_MARGIN_CM
    ):
        detected = "left"

    elif (
        right_drop >= THRESHOLD_CM
        and right_drop >= left_drop + DOMINANCE_MARGIN_CM
    ):
        detected = "right"

    print(f"DETECTED SIDE: {detected.upper()}")
    print(f"EXPECTED SIDE: {expected_side.upper()}")

    if detected == expected_side:
        print("RESULT: PASS — direct-Pi side detection works.")
    elif detected == "unknown":
        print("RESULT: INCONCLUSIVE — move the object closer/larger and repeat.")
    else:
        print("RESULT: FAIL — unexpected side detected. Check sensor placement.")


if __name__ == "__main__":
    main()
