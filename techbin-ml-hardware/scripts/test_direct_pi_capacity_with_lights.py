#!/usr/bin/env python3
"""
TechBin direct-Pi end-to-end capacity + traffic-light test.

Reads left/right HC-SR04 sequentially and controls:
- Green  : below 40%
- Yellow : 40% to below 80%
- Red    : 80% and above

Press Ctrl+C to stop. All LEDs turn off safely.
"""

from __future__ import annotations

import statistics
import time

from gpiozero import DistanceSensor, LED


# Real direct-Pi wiring
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

LIGHTS = {
    "left": {
        "red": LED(17, active_high=True, initial_value=False),
        "yellow": LED(27, active_high=True, initial_value=False),
        "green": LED(22, active_high=True, initial_value=False),
    },
    "right": {
        "red": LED(12, active_high=True, initial_value=False),
        "yellow": LED(13, active_high=True, initial_value=False),
        "green": LED(26, active_high=True, initial_value=False),
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
        time.sleep(0.35)

        for _ in range(5):
            value = sensor.distance * 100.0
            if 2.0 <= value < 79.5:
                values.append(value)
            time.sleep(0.12)
    finally:
        sensor.close()

    if len(values) < 4:
        raise RuntimeError(f"{side}: insufficient valid readings: {values}")

    return statistics.median(values)


def calculate_fill_percent(side: str, distance_cm: float) -> float:
    cfg = SENSORS[side]

    raw = (
        (cfg["empty_cm"] - distance_cm)
        / (cfg["empty_cm"] - cfg["full_cm"])
    ) * 100.0

    return max(0.0, min(100.0, raw))


def capacity_colour(fill_percent: float) -> str:
    if fill_percent < YELLOW_START_PERCENT:
        return "green"

    if fill_percent < RED_START_PERCENT:
        return "yellow"

    return "red"


def set_light(side: str, colour: str) -> None:
    for name, led in LIGHTS[side].items():
        if name == colour:
            led.on()
        else:
            led.off()


def all_lights_off() -> None:
    for side_lights in LIGHTS.values():
        for led in side_lights.values():
            led.off()


def main() -> None:
    print()
    print("=== TechBin End-to-End Capacity + Traffic-Light Test ===")
    print("Green: below 40% | Yellow: 40% to below 80% | Red: 80%+")
    print("Press Ctrl+C to stop safely.")
    print()

    try:
        while True:
            left_distance = read_median_cm("left")
            time.sleep(0.25)

            right_distance = read_median_cm("right")

            left_fill = calculate_fill_percent("left", left_distance)
            right_fill = calculate_fill_percent("right", right_distance)

            left_colour = capacity_colour(left_fill)
            right_colour = capacity_colour(right_fill)

            set_light("left", left_colour)
            set_light("right", right_colour)

            print(
                f"LEFT  | {left_distance:5.2f} cm | "
                f"{left_fill:5.1f}% | {left_colour.upper()}"
            )
            print(
                f"RIGHT | {right_distance:5.2f} cm | "
                f"{right_fill:5.1f}% | {right_colour.upper()}"
            )
            print("-" * 58)

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping test...")

    finally:
        all_lights_off()

        for side_lights in LIGHTS.values():
            for led in side_lights.values():
                led.close()

        print("All traffic-light LEDs are OFF.")


if __name__ == "__main__":
    main()
