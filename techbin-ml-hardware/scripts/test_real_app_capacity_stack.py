#!/usr/bin/env python3
"""
Run the real TechBin direct-Pi capacity + traffic-light stack.
Press Ctrl+C to stop. Both traffic lights turn off safely.
"""

from __future__ import annotations

import time

from app.sensors.direct_pi_stack import build_direct_pi_hardware_stack


def print_result(result) -> None:
    for label, data in (("LEFT", result.left), ("RIGHT", result.right)):
        fill = data.get("fillLevel", {})
        indicator = data.get("indicatorState", {})

        print(
            f"{label:5} | "
            f"distance={fill.get('distanceCm')} cm | "
            f"fill={fill.get('fillPercentage')}% | "
            f"light={indicator.get('activeColor')} | "
            f"valid={data.get('valid')}"
        )

    print("-" * 72)


def main() -> None:
    stack = build_direct_pi_hardware_stack()

    print()
    print("=== TechBin Real Application Capacity + Light Test ===")
    print("Uses real app calibration, app capacity monitor, and app indicators.")
    print("Press Ctrl+C to stop safely.")
    print()

    try:
        while True:
            result = stack.capacity_monitor.check_all()
            print_result(result)
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping direct-Pi application test...")

    finally:
        stack.close()
        print("Both traffic lights are OFF; GPIO resources released.")


if __name__ == "__main__":
    main()
