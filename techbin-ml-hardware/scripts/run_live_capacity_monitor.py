#!/usr/bin/env python3
"""
Keeps TechBin compartment traffic lights active while this program runs.
Refreshes both compartment capacities every few seconds.
"""

from __future__ import annotations

import time

from app.sensors.direct_pi_stack import build_direct_pi_hardware_stack

CHECK_INTERVAL_SECONDS = 3.0


def print_compartment(label: str, data: dict) -> None:
    fill = data.get("fillLevel", {})
    indicator = data.get("indicatorState", {})

    print(
        f"{label:5} | "
        f"distance={fill.get('distanceCm')} cm | "
        f"fill={fill.get('fillPercentage')}% | "
        f"level={fill.get('level')} | "
        f"light={indicator.get('activeColor')}"
    )


def main() -> None:
    stack = build_direct_pi_hardware_stack()

    try:
        print()
        print("=== TechBin Live Capacity Monitor ===")
        print("Traffic lights remain active while this program is running.")
        print("Press Ctrl+C to stop safely.")
        print()

        while True:
            result = stack.capacity_monitor.check_all().to_dict()

            print("-" * 64)
            print_compartment("LEFT", result["left"])
            print_compartment("RIGHT", result["right"])

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nLive capacity monitor stopped.")

    finally:
        stack.close()
        print("GPIO resources released; traffic lights are OFF.")


if __name__ == "__main__":
    main()
