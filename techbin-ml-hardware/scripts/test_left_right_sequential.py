#!/usr/bin/env python3
"""
TechBin direct-Pi left/right HC-SR04 sequential test.

Only one sensor is active at a time to avoid ultrasonic echo interference.
"""

from __future__ import annotations

import statistics
import time

from gpiozero import DistanceSensor


def read_one(name: str, trigger: int, echo: int) -> float | None:
    sensor = None

    try:
        sensor = DistanceSensor(
            trigger=trigger,
            echo=echo,
            max_distance=0.80,
            queue_len=1,
            partial=True,
        )

        # Let this sensor collect a fresh reading.
        time.sleep(0.35)

        distance_cm = sensor.distance * 100.0

        if not 2.0 <= distance_cm < 79.5:
            print(f"{name}: invalid reading {distance_cm:.2f} cm")
            return None

        return distance_cm

    except Exception as exc:
        print(f"{name}: ERROR: {exc}")
        return None

    finally:
        if sensor is not None:
            sensor.close()


def summary(name: str, values: list[float]) -> None:
    if not values:
        print(f"{name}: no valid readings")
        return

    print(
        f"{name}: median={statistics.median(values):.2f} cm | "
        f"range={min(values):.2f}–{max(values):.2f} cm"
    )


def main() -> None:
    left_values: list[float] = []
    right_values: list[float] = []

    print()
    print("=== TechBin Left/Right Sequential HC-SR04 Test ===")
    print("Keep both compartments empty during this test.")
    print()

    for cycle in range(1, 11):
        left = read_one("LEFT", trigger=5, echo=6)

        # Wait so the left echo fully disappears before right is triggered.
        time.sleep(0.20)

        right = read_one("RIGHT", trigger=16, echo=20)

        if left is not None:
            left_values.append(left)

        if right is not None:
            right_values.append(right)

        left_text = f"{left:.2f} cm" if left is not None else "INVALID"
        right_text = f"{right:.2f} cm" if right is not None else "INVALID"

        print(f"Cycle {cycle:02d} | Left: {left_text} | Right: {right_text}")

        time.sleep(0.50)

    print()
    print("=== Summary ===")
    summary("Left", left_values)
    summary("Right", right_values)


if __name__ == "__main__":
    main()
