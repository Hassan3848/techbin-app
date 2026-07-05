#!/usr/bin/env python3
"""
Direct-Pi capacity test for TechBin left/right HC-SR04 sensors.
Prints fill percentage and expected traffic-light color.
"""

from __future__ import annotations

import statistics
import time

from gpiozero import DistanceSensor


SENSORS = {
    "left": {
        "trigger": 5,
        "echo": 6,
        "empty_cm": 38.20,
        "full_cm": 5.00,
    },
    "right": {
        "trigger": 16,
        "echo": 20,
        "empty_cm": 39.00,
        "full_cm": 5.00,
    },
}

YELLOW_START_PERCENT = 40.0
RED_START_PERCENT = 80.0


def read_median_cm(side: str) -> float:
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

        for _ in range(7):
            distance_cm = sensor.distance * 100.0
            if 2.0 <= distance_cm < 79.5:
                values.append(distance_cm)
            time.sleep(0.2)

    finally:
        sensor.close()

    if len(values) < 5:
        raise RuntimeError(f"{side}: insufficient valid readings: {values}")

    return statistics.median(values)


def fill_percent(distance_cm: float, empty_cm: float, full_cm: float) -> float:
    raw = ((empty_cm - distance_cm) / (empty_cm - full_cm)) * 100.0
    return max(0.0, min(100.0, raw))


def traffic_state(percent: float) -> str:
    if percent < YELLOW_START_PERCENT:
        return "GREEN — low fill"
    if percent < RED_START_PERCENT:
        return "YELLOW — medium fill"
    return "RED — high/full"


def print_result(side: str, distance_cm: float) -> None:
    cfg = SENSORS[side]
    percent = fill_percent(distance_cm, cfg["empty_cm"], cfg["full_cm"])

    print(
        f"{side.upper():5} | "
        f"distance={distance_cm:5.2f} cm | "
        f"fill={percent:5.1f}% | "
        f"expected light: {traffic_state(percent)}"
    )


def main() -> None:
    print()
    print("=== TechBin Direct-Pi Capacity Test ===")
    print("Reading sensors sequentially. No traffic lights are controlled yet.")
    print()

    left_cm = read_median_cm("left")
    time.sleep(0.35)
    right_cm = read_median_cm("right")

    print_result("left", left_cm)
    print_result("right", right_cm)


if __name__ == "__main__":
    main()
