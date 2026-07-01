"""
HC-SR04 ultrasonic sensor support for TechBin.

Purpose:
    Read ultrasonic distance sensors safely and consistently.

Important hardware safety:
    HC-SR04 Echo output is 5V.
    Raspberry Pi GPIO is 3.3V.
    Echo must go through a resistor divider or proper level shifter.

Current production behavior:
    - Supports simulated backend for safe tests
    - Supports real gpiozero backend for later hardware testing
    - Produces structured readings instead of raw floats
    - Handles invalid distances, timeouts, and backend failures
    - Supports median filtering over multiple samples

Sensor roles planned:
    front_ultrasonic -> user/session detection
    left_ultrasonic  -> left compartment disturbance/fill support
    right_ultrasonic -> right compartment disturbance/fill support
"""

from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol

from app.logger import get_logger
from app.sensors.pin_map import UltrasonicSensorPins


logger = get_logger(__name__)


class UltrasonicSensorError(RuntimeError):
    """Raised when ultrasonic sensor setup or reading fails."""


@dataclass(frozen=True)
class UltrasonicSensorConfig:
    """
    Runtime configuration for one ultrasonic sensor.

    All GPIO values are BCM GPIO numbers.
    """

    name: str
    trigger_gpio: int
    echo_gpio: int
    role: str
    enabled: bool = False
    min_distance_cm: float = 2.0
    max_distance_cm: float = 400.0
    timeout_seconds: float = 0.04
    samples: int = 5
    sample_delay_seconds: float = 0.06

    @classmethod
    def from_pin_config(
        cls,
        pin_config: UltrasonicSensorPins,
        *,
        enabled: bool | None = None,
        min_distance_cm: float = 2.0,
        max_distance_cm: float = 400.0,
        timeout_seconds: float = 0.04,
        samples: int = 5,
        sample_delay_seconds: float = 0.06,
    ) -> "UltrasonicSensorConfig":
        """
        Build runtime config from pin_map.py config.
        """

        return cls(
            name=pin_config.name,
            trigger_gpio=pin_config.trigger_gpio,
            echo_gpio=pin_config.echo_gpio,
            role=pin_config.role,
            enabled=pin_config.enabled if enabled is None else enabled,
            min_distance_cm=min_distance_cm,
            max_distance_cm=max_distance_cm,
            timeout_seconds=timeout_seconds,
            samples=samples,
            sample_delay_seconds=sample_delay_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UltrasonicReading:
    """
    Structured result of an ultrasonic distance read.
    """

    sensorName: str
    role: str
    timestamp: str
    distanceCm: float | None
    rawReadingsCm: list[float]
    valid: bool
    faultCode: str | None
    message: str
    triggerGpio: int
    echoGpio: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UltrasonicBackend(Protocol):
    """
    Backend interface for ultrasonic distance reading.
    """

    def measure_distance_cm(self, config: UltrasonicSensorConfig) -> float:
        """
        Return one distance measurement in centimeters.
        """


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _validate_config(config: UltrasonicSensorConfig) -> None:
    """
    Validate ultrasonic sensor configuration.
    """

    if not config.name.strip():
        raise UltrasonicSensorError("Sensor name cannot be empty")

    if not config.role.strip():
        raise UltrasonicSensorError("Sensor role cannot be empty")

    if config.trigger_gpio == config.echo_gpio:
        raise UltrasonicSensorError(
            f"{config.name}: trigger_gpio and echo_gpio cannot be the same"
        )

    for pin_name, pin_value in (
        ("trigger_gpio", config.trigger_gpio),
        ("echo_gpio", config.echo_gpio),
    ):
        if not isinstance(pin_value, int) or pin_value < 0 or pin_value > 27:
            raise UltrasonicSensorError(
                f"{config.name}: invalid {pin_name}: {pin_value}"
            )

    if config.min_distance_cm <= 0:
        raise UltrasonicSensorError(
            f"{config.name}: min_distance_cm must be positive"
        )

    if config.max_distance_cm <= config.min_distance_cm:
        raise UltrasonicSensorError(
            f"{config.name}: max_distance_cm must be greater than min_distance_cm"
        )

    if config.timeout_seconds <= 0:
        raise UltrasonicSensorError(
            f"{config.name}: timeout_seconds must be positive"
        )

    if config.samples <= 0:
        raise UltrasonicSensorError(
            f"{config.name}: samples must be greater than zero"
        )

    if config.sample_delay_seconds < 0:
        raise UltrasonicSensorError(
            f"{config.name}: sample_delay_seconds cannot be negative"
        )


class SimulatedUltrasonicBackend:
    """
    Safe simulated backend for tests and development.

    This backend does not use GPIO.
    """

    def __init__(
        self,
        fixed_distance_cm: float = 100.0,
        sequence_cm: list[float] | tuple[float, ...] | None = None,
    ) -> None:
        self.fixed_distance_cm = fixed_distance_cm
        self.sequence_cm = list(sequence_cm or [])
        self._index = 0

    def measure_distance_cm(self, config: UltrasonicSensorConfig) -> float:
        if self.sequence_cm:
            value = self.sequence_cm[self._index % len(self.sequence_cm)]
            self._index += 1
            return float(value)

        return float(self.fixed_distance_cm)


class GpioZeroUltrasonicBackend:
    """
    Real GPIO backend using gpiozero.DistanceSensor.

    Use only after HC-SR04 Echo is safely level shifted to 3.3V.

    Install if missing:
        sudo apt install -y python3-gpiozero
    """

    def __init__(self) -> None:
        try:
            from gpiozero import DistanceSensor
        except ImportError as exc:
            raise UltrasonicSensorError(
                "gpiozero is required for real ultrasonic reads. "
                "Install with: sudo apt install -y python3-gpiozero"
            ) from exc

        self._distance_sensor_class = DistanceSensor
        self._sensors: dict[str, Any] = {}

    def _get_sensor(self, config: UltrasonicSensorConfig):
        key = f"{config.name}:{config.trigger_gpio}:{config.echo_gpio}"

        if key not in self._sensors:
            # gpiozero max_distance is in meters.
            max_distance_m = config.max_distance_cm / 100.0

            self._sensors[key] = self._distance_sensor_class(
                echo=config.echo_gpio,
                trigger=config.trigger_gpio,
                max_distance=max_distance_m,
            )

        return self._sensors[key]

    def measure_distance_cm(self, config: UltrasonicSensorConfig) -> float:
        sensor = self._get_sensor(config)

        start = time.perf_counter()

        while True:
            distance_m = sensor.distance

            if distance_m is not None:
                return float(distance_m) * 100.0

            if time.perf_counter() - start > config.timeout_seconds:
                raise UltrasonicSensorError(
                    f"{config.name}: ultrasonic echo timeout"
                )

            time.sleep(0.002)

    def close(self) -> None:
        """
        Close gpiozero sensor objects.
        """

        for sensor in self._sensors.values():
            if hasattr(sensor, "close"):
                sensor.close()

        self._sensors.clear()


class UltrasonicDistanceSensor:
    """
    Production wrapper for one ultrasonic sensor.
    """

    def __init__(
        self,
        config: UltrasonicSensorConfig,
        backend: UltrasonicBackend | None = None,
    ) -> None:
        _validate_config(config)

        self.config = config
        self.backend = backend or SimulatedUltrasonicBackend()

    def read_once(self) -> UltrasonicReading:
        """
        Read one distance sample.
        """

        if not self.config.enabled:
            return UltrasonicReading(
                sensorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                distanceCm=None,
                rawReadingsCm=[],
                valid=False,
                faultCode="ultrasonic_not_enabled",
                message="Ultrasonic sensor is not enabled in configuration.",
                triggerGpio=self.config.trigger_gpio,
                echoGpio=self.config.echo_gpio,
            )

        try:
            distance_cm = float(self.backend.measure_distance_cm(self.config))

            if distance_cm < self.config.min_distance_cm:
                return UltrasonicReading(
                    sensorName=self.config.name,
                    role=self.config.role,
                    timestamp=_now_iso(),
                    distanceCm=distance_cm,
                    rawReadingsCm=[distance_cm],
                    valid=False,
                    faultCode="ultrasonic_distance_too_small",
                    message=(
                        f"Distance {distance_cm:.2f}cm is below minimum "
                        f"{self.config.min_distance_cm:.2f}cm."
                    ),
                    triggerGpio=self.config.trigger_gpio,
                    echoGpio=self.config.echo_gpio,
                )

            if distance_cm > self.config.max_distance_cm:
                return UltrasonicReading(
                    sensorName=self.config.name,
                    role=self.config.role,
                    timestamp=_now_iso(),
                    distanceCm=distance_cm,
                    rawReadingsCm=[distance_cm],
                    valid=False,
                    faultCode="ultrasonic_distance_too_large",
                    message=(
                        f"Distance {distance_cm:.2f}cm is above maximum "
                        f"{self.config.max_distance_cm:.2f}cm."
                    ),
                    triggerGpio=self.config.trigger_gpio,
                    echoGpio=self.config.echo_gpio,
                )

            return UltrasonicReading(
                sensorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                distanceCm=round(distance_cm, 2),
                rawReadingsCm=[round(distance_cm, 2)],
                valid=True,
                faultCode=None,
                message="Distance reading is valid.",
                triggerGpio=self.config.trigger_gpio,
                echoGpio=self.config.echo_gpio,
            )

        except Exception as exc:
            logger.warning(
                "Ultrasonic read failed | sensor=%s | error=%s",
                self.config.name,
                exc,
            )

            return UltrasonicReading(
                sensorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                distanceCm=None,
                rawReadingsCm=[],
                valid=False,
                faultCode="ultrasonic_read_failed",
                message=str(exc),
                triggerGpio=self.config.trigger_gpio,
                echoGpio=self.config.echo_gpio,
            )

    def read_filtered(self) -> UltrasonicReading:
        """
        Read multiple samples and return median-filtered distance.

        Invalid samples are skipped.
        If no valid sample remains, returns a fault reading.
        """

        if not self.config.enabled:
            return self.read_once()

        valid_distances: list[float] = []
        raw_distances: list[float] = []
        fault_codes: list[str] = []

        for index in range(self.config.samples):
            reading = self.read_once()

            if reading.distanceCm is not None:
                raw_distances.extend(reading.rawReadingsCm)

            if reading.valid and reading.distanceCm is not None:
                valid_distances.append(float(reading.distanceCm))
            elif reading.faultCode:
                fault_codes.append(reading.faultCode)

            if index < self.config.samples - 1 and self.config.sample_delay_seconds > 0:
                time.sleep(self.config.sample_delay_seconds)

        if not valid_distances:
            fault_code = (
                "ultrasonic_no_valid_samples"
                if not fault_codes
                else f"ultrasonic_no_valid_samples:{','.join(sorted(set(fault_codes)))}"
            )

            return UltrasonicReading(
                sensorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                distanceCm=None,
                rawReadingsCm=[round(value, 2) for value in raw_distances],
                valid=False,
                faultCode=fault_code,
                message="No valid ultrasonic samples were collected.",
                triggerGpio=self.config.trigger_gpio,
                echoGpio=self.config.echo_gpio,
            )

        median_distance = statistics.median(valid_distances)

        return UltrasonicReading(
            sensorName=self.config.name,
            role=self.config.role,
            timestamp=_now_iso(),
            distanceCm=round(float(median_distance), 2),
            rawReadingsCm=[round(value, 2) for value in raw_distances],
            valid=True,
            faultCode=None,
            message="Median-filtered distance reading is valid.",
            triggerGpio=self.config.trigger_gpio,
            echoGpio=self.config.echo_gpio,
        )


def build_sensor_from_pin_config(
    pin_config: UltrasonicSensorPins,
    *,
    enabled: bool | None = None,
    backend: UltrasonicBackend | None = None,
    samples: int = 5,
) -> UltrasonicDistanceSensor:
    """
    Build UltrasonicDistanceSensor from central pin map config.
    """

    config = UltrasonicSensorConfig.from_pin_config(
        pin_config,
        enabled=enabled,
        samples=samples,
    )

    return UltrasonicDistanceSensor(
        config=config,
        backend=backend,
    )


__all__ = [
    "UltrasonicSensorError",
    "UltrasonicSensorConfig",
    "UltrasonicReading",
    "UltrasonicBackend",
    "SimulatedUltrasonicBackend",
    "GpioZeroUltrasonicBackend",
    "UltrasonicDistanceSensor",
    "build_sensor_from_pin_config",
]
