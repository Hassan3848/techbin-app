"""
TechBin direct Raspberry Pi hardware factory.

Builds the verified direct-Pi sensor/indicator stack:
- front HC-SR04 for session detection
- left/right HC-SR04 for capacity and disposal-side confirmation
- left/right traffic lights for fill state
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.sensors.capacity_calibration import (
    techbin_left_fill_config,
    techbin_right_fill_config,
)
from app.sensors.capacity_indicator import (
    DualCapacityIndicators,
    GpioZeroCapacityIndicatorBackend,
    build_dual_capacity_indicators,
)
from app.sensors.capacity_monitor import (
    CompartmentCapacityMonitor,
    DualCapacityMonitor,
)
from app.sensors.pin_map import PIN_MAP, UltrasonicSensorPins
from app.sensors.session_detector import (
    FrontSessionDetector,
    SessionDetectorConfig,
)
from app.sensors.side_detector import (
    DualUltrasonicSideDetector,
    SideDetectionConfig,
)
from app.sensors.ultrasonic import (
    UltrasonicBackend,
    UltrasonicDistanceSensor,
    UltrasonicSensorConfig,
    UltrasonicSensorError,
)


class DirectPiHardwareError(RuntimeError):
    """Raised when the direct-Pi hardware stack cannot be built."""


class SequentialGpioZeroUltrasonicBackend:
    """
    Measure one HC-SR04 at a time.

    Keeping three gpiozero DistanceSensor objects alive can create ultrasonic
    echo interference. This backend creates one temporary object per reading,
    waits for a fresh value, then closes it before another sensor is triggered.
    """

    def __init__(
        self,
        *,
        settle_seconds: float = 0.35,
        timeout_as_distance_cm: float | None = None,
    ) -> None:
        try:
            from gpiozero import DistanceSensor
        except ImportError as exc:
            raise DirectPiHardwareError(
                "gpiozero is required for direct Pi ultrasonic hardware."
            ) from exc

        self._distance_sensor_class = DistanceSensor
        self.settle_seconds = float(settle_seconds)
        self.timeout_as_distance_cm = timeout_as_distance_cm

    def measure_distance_cm(self, config: UltrasonicSensorConfig) -> float:
        sensor = None

        try:
            sensor = self._distance_sensor_class(
                trigger=config.trigger_gpio,
                echo=config.echo_gpio,
                max_distance=config.max_distance_cm / 100.0,
                queue_len=1,
                partial=True,
            )

            time.sleep(self.settle_seconds)

            distance_cm = float(sensor.distance) * 100.0

            if distance_cm >= config.max_distance_cm - 0.25:
                if self.timeout_as_distance_cm is not None:
                    return float(self.timeout_as_distance_cm)

                raise UltrasonicSensorError(
                    f"{config.name}: ultrasonic echo timeout or out-of-range reading"
                )

            return distance_cm

        finally:
            if sensor is not None and hasattr(sensor, "close"):
                sensor.close()

    def close(self) -> None:
        return None


def _require_enabled(pin_config: UltrasonicSensorPins) -> None:
    if not pin_config.enabled:
        raise DirectPiHardwareError(
            f"{pin_config.name} is disabled in app/sensors/pin_map.py"
        )


def _build_sensor(
    *,
    pin_config: UltrasonicSensorPins,
    backend: UltrasonicBackend,
    samples: int,
    max_distance_cm: float,
) -> UltrasonicDistanceSensor:
    _require_enabled(pin_config)

    config = UltrasonicSensorConfig.from_pin_config(
        pin_config,
        enabled=True,
        min_distance_cm=2.0,
        max_distance_cm=max_distance_cm,
        timeout_seconds=0.10,
        samples=samples,
        sample_delay_seconds=0.08,
    )

    return UltrasonicDistanceSensor(config=config, backend=backend)


@dataclass
class DirectPiHardwareStack:
    ultrasonic_backend: SequentialGpioZeroUltrasonicBackend
    front_session_backend: SequentialGpioZeroUltrasonicBackend
    indicator_backend: GpioZeroCapacityIndicatorBackend
    front_sensor: UltrasonicDistanceSensor
    left_capacity_sensor: UltrasonicDistanceSensor
    right_capacity_sensor: UltrasonicDistanceSensor
    left_side_sensor: UltrasonicDistanceSensor
    right_side_sensor: UltrasonicDistanceSensor
    session_detector: FrontSessionDetector
    side_detector: DualUltrasonicSideDetector
    indicators: DualCapacityIndicators
    capacity_monitor: DualCapacityMonitor

    def close(self) -> None:
        try:
            self.indicators.off()
        except Exception:
            pass

        self.indicator_backend.close()
        self.ultrasonic_backend.close()
        self.front_session_backend.close()


def build_direct_pi_hardware_stack() -> DirectPiHardwareStack:
    required = (
        PIN_MAP.ultrasonic_front,
        PIN_MAP.ultrasonic_left,
        PIN_MAP.ultrasonic_right,
    )

    for pin_config in required:
        _require_enabled(pin_config)

    if not PIN_MAP.traffic_light_left.enabled:
        raise DirectPiHardwareError("Left traffic light is disabled in pin_map.py")

    if not PIN_MAP.traffic_light_right.enabled:
        raise DirectPiHardwareError("Right traffic light is disabled in pin_map.py")

    ultrasonic_backend = SequentialGpioZeroUltrasonicBackend(settle_seconds=0.35)

    # For the front user/session sensor only, no echo means no nearby user.
    # Capacity and disposal-side sensors remain strict and report timeouts.
    front_session_backend = SequentialGpioZeroUltrasonicBackend(
        settle_seconds=0.35,
        timeout_as_distance_cm=100.0,
    )

    indicator_backend = GpioZeroCapacityIndicatorBackend()

    front_sensor = _build_sensor(
        pin_config=PIN_MAP.ultrasonic_front,
        backend=front_session_backend,
        samples=1,
        max_distance_cm=200.0,
    )

    left_capacity_sensor = _build_sensor(
        pin_config=PIN_MAP.ultrasonic_left,
        backend=ultrasonic_backend,
        samples=3,
        max_distance_cm=80.0,
    )

    right_capacity_sensor = _build_sensor(
        pin_config=PIN_MAP.ultrasonic_right,
        backend=ultrasonic_backend,
        samples=3,
        max_distance_cm=80.0,
    )

    left_side_sensor = _build_sensor(
        pin_config=PIN_MAP.ultrasonic_left,
        backend=ultrasonic_backend,
        samples=1,
        max_distance_cm=80.0,
    )

    right_side_sensor = _build_sensor(
        pin_config=PIN_MAP.ultrasonic_right,
        backend=ultrasonic_backend,
        samples=1,
        max_distance_cm=80.0,
    )

    indicators = build_dual_capacity_indicators(
        left_pin_config=PIN_MAP.traffic_light_left,
        right_pin_config=PIN_MAP.traffic_light_right,
        enabled=True,
        backend=indicator_backend,
    )

    capacity_monitor = DualCapacityMonitor(
        left_monitor=CompartmentCapacityMonitor(
            compartment_name="left_compartment",
            ultrasonic_sensor=left_capacity_sensor,
            fill_config=techbin_left_fill_config(),
            indicator=indicators.left,
            update_indicator=True,
        ),
        right_monitor=CompartmentCapacityMonitor(
            compartment_name="right_compartment",
            ultrasonic_sensor=right_capacity_sensor,
            fill_config=techbin_right_fill_config(),
            indicator=indicators.right,
            update_indicator=True,
        ),
    )

    session_detector = FrontSessionDetector(
        front_sensor,
        config=SessionDetectorConfig(
            presence_threshold_cm=35.0,
            stable_presence_reads=2,
            stable_absence_reads=3,
        ),
    )

    side_detector = DualUltrasonicSideDetector(
        left_sensor=left_side_sensor,
        right_sensor=right_side_sensor,
        config=SideDetectionConfig(
            disturbance_threshold_cm=5.0,
            dominance_margin_cm=6.0,
            use_absolute_delta=False,
            inter_sensor_delay_seconds=0.25,
        ),
    )

    return DirectPiHardwareStack(
        ultrasonic_backend=ultrasonic_backend,
        front_session_backend=front_session_backend,
        indicator_backend=indicator_backend,
        front_sensor=front_sensor,
        left_capacity_sensor=left_capacity_sensor,
        right_capacity_sensor=right_capacity_sensor,
        left_side_sensor=left_side_sensor,
        right_side_sensor=right_side_sensor,
        session_detector=session_detector,
        side_detector=side_detector,
        indicators=indicators,
        capacity_monitor=capacity_monitor,
    )


__all__ = [
    "DirectPiHardwareError",
    "SequentialGpioZeroUltrasonicBackend",
    "DirectPiHardwareStack",
    "build_direct_pi_hardware_stack",
]
