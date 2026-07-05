#!/usr/bin/env python3
"""
Test TechBin's real front ultrasonic session detector.

Expected behavior:
- No person/object near front sensor -> sessionActive=False
- Object/person within threshold for stable reads -> sessionActive=True
- Object/person removed -> sessionActive=False after stable absence reads
"""

from __future__ import annotations

import time

from app.sensors.direct_pi_stack import build_direct_pi_hardware_stack


def main() -> None:
    stack = build_direct_pi_hardware_stack()

    print()
    print("=== TechBin Real App Front Session Test ===")
    print("Front sensor threshold: about 35 cm")
    print("Press Ctrl+C to stop safely.")
    print()

    try:
        while True:
            result = stack.session_detector.update()
            data = result.to_dict()

            ultrasonic = data.get("ultrasonicReading") or {}
            distance = ultrasonic.get("distanceCm")

            state = (
                data.get("sessionState")
                or data.get("state")
                or data.get("status")
                or "unknown"
            )

            print(
                f"distance={distance} cm | "
                f"sessionActive={data.get('sessionActive')} | "
                f"state={state} | "
                f"valid={data.get('valid')} | "
                f"message={data.get('message')}"
            )

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping front-session test...")

    finally:
        stack.close()
        print("GPIO resources released; traffic lights are OFF.")


if __name__ == "__main__":
    main()
