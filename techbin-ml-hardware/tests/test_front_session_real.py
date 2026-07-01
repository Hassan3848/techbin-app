"""
Real hardware test for TechBin front session detector.

Uses:
    Front HC-SR04 ultrasonic sensor

Wiring:
    Front TRIG -> GPIO23 / physical pin 16
    Front ECHO -> 10k/10k divider -> GPIO24 / physical pin 18

Run:
    PYTHONPATH=. python3 tests/test_front_session_real.py

Stop:
    CTRL+C
"""

from __future__ import annotations

import time

from app.sensors.pin_map import PIN_MAP
from app.sensors.session_detector import FrontSessionDetector, SessionDetectorConfig
from app.sensors.ultrasonic import GpioZeroUltrasonicBackend, build_sensor_from_pin_config


def main() -> None:
    print()
    print("========== Real Front Session Detector Test ==========")
    print("Move your hand/object within about 35 cm of the front sensor.")
    print("Expected:")
    print("  far  -> idle")
    print("  near -> presence_candidate / active")
    print("  far again -> ending_candidate / ended")
    print("Press CTRL+C to stop.")
    print("======================================================")
    print()

    backend = GpioZeroUltrasonicBackend()

    front_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=backend,
        samples=3,
    )

    detector = FrontSessionDetector(
        front_sensor,
        config=SessionDetectorConfig(
            presence_threshold_cm=35.0,
            stable_presence_reads=2,
            stable_absence_reads=3,
        ),
    )

    try:
        while True:
            result = detector.update()

            print(
                f"distance={str(result.distanceCm).rjust(6)} cm | "
                f"presence={str(result.presenceDetected).ljust(5)} | "
                f"state={result.state.ljust(18)} | "
                f"active={result.sessionActive} | "
                f"started={result.sessionStarted} | "
                f"ended={result.sessionEnded}"
            )

            time.sleep(0.5)

    except KeyboardInterrupt:
        print()
        print("Stopped front session detector test.")

    finally:
        backend.close()


if __name__ == "__main__":
    main()
