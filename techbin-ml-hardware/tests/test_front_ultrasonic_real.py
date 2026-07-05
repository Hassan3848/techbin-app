"""
Real hardware test for TechBin front HC-SR04 ultrasonic sensor.

Wiring:
    Front TRIG -> GPIO23 / physical pin 16
    Front ECHO -> 10k/10k divider -> GPIO24 / physical pin 18

Run:
    PYTHONPATH=. python3 tests/test_front_ultrasonic_real.py

Stop:
    CTRL+C
"""

from __future__ import annotations

import time

from app.sensors.pin_map import PIN_MAP
from app.sensors.ultrasonic import (
    GpioZeroUltrasonicBackend,
    build_sensor_from_pin_config,
)


def main() -> None:
    print()
    print("========== Real Front Ultrasonic Test ==========")
    print("Sensor: front_ultrasonic")
    print("TRIG: GPIO23 / physical pin 16")
    print("ECHO: GPIO24 / physical pin 18 through 10k/10k divider")
    print("Move your hand/object in front of the sensor.")
    print("Press CTRL+C to stop.")
    print("================================================")
    print()

    backend = GpioZeroUltrasonicBackend()

    sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=backend,
        samples=5,
    )

    try:
        while True:
            reading = sensor.read_filtered()

            if reading.valid:
                print(f"front_ultrasonic distance: {reading.distanceCm:7.2f} cm")
            else:
                print(
                    "front_ultrasonic fault:",
                    reading.faultCode,
                    "|",
                    reading.message,
                )

            time.sleep(0.5)

    except KeyboardInterrupt:
        print()
        print("Stopped front ultrasonic test.")

    finally:
        backend.close()


if __name__ == "__main__":
    main()
