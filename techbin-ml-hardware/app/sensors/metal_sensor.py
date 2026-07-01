"""
Omron inductive metal sensor support for TechBin.

Purpose:
    Read metal detection signal safely and consistently.

Important hardware safety:
    Omron E2E-X5ME1-Z must NOT be connected directly to Raspberry Pi GPIO
    unless proper interfacing/isolation has been designed and verified.

Current production behavior:
    - Supports simulated backend for safe tests
    - Supports real gpiozero backend for future hardware use
    - Supports active HIGH / active LOW sensor logic
    - Supports debounced reading
    - Supports stuck HIGH / stuck LOW health checks
    - Produces structured readings instead of raw booleans

Product rule:
    Metal sensor is a confidence booster, not the sole truth source.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol

from app.logger import get_logger
from app.sensors.pin_map import MetalSensorPins


logger = get_logger(__name__)


class MetalSensorError(RuntimeError):
    """Raised when metal sensor setup or reading fails."""


@dataclass(frozen=True)
class MetalSensorConfig:
    """
    Runtime configuration for Omron metal sensor input.

    signal_gpio:
        BCM GPIO pin number.

    active_low:
        False means HIGH = metal detected.
        True means LOW = metal detected.
    """

    name: str = "metal_sensor"
    signal_gpio: int = 21
    enabled: bool = False
    active_low: bool = False
    samples: int = 5
    sample_delay_seconds: float = 0.03

    @classmethod
    def from_pin_config(
        cls,
        pin_config: MetalSensorPins,
        *,
        enabled: bool | None = None,
        samples: int = 5,
        sample_delay_seconds: float = 0.03,
    ) -> "MetalSensorConfig":
        return cls(
            signal_gpio=pin_config.signal_gpio,
            enabled=pin_config.enabled if enabled is None else enabled,
            active_low=pin_config.active_low,
            samples=samples,
            sample_delay_seconds=sample_delay_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetalSensorReading:
    """
    Structured result of one metal sensor read.
    """

    sensorName: str
    timestamp: str
    metalDetected: bool | None
    rawValues: list[bool]
    valid: bool
    faultCode: str | None
    message: str
    signalGpio: int
    activeLow: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetalSensorHealth:
    """
    Health status for metal sensor signal behavior.
    """

    sensorName: str
    timestamp: str
    ok: bool
    status: str
    faultCode: str | None
    message: str
    signalGpio: int
    activeLow: bool
    samplesChecked: int
    highCount: int
    lowCount: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetalSensorBackend(Protocol):
    """
    Backend interface for metal sensor signal reading.
    """

    def read_signal(self, config: MetalSensorConfig) -> bool:
        """
        Return raw digital signal.

        True means GPIO HIGH.
        False means GPIO LOW.
        """


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _validate_config(config: MetalSensorConfig) -> None:
    if not config.name.strip():
        raise MetalSensorError("Metal sensor name cannot be empty")

    if not isinstance(config.signal_gpio, int) or config.signal_gpio < 0 or config.signal_gpio > 27:
        raise MetalSensorError(f"Invalid BCM GPIO pin: {config.signal_gpio}")

    if config.samples <= 0:
        raise MetalSensorError("samples must be greater than zero")

    if config.sample_delay_seconds < 0:
        raise MetalSensorError("sample_delay_seconds cannot be negative")


def _raw_to_metal_detected(raw_signal: bool, active_low: bool) -> bool:
    """
    Convert raw GPIO level into metal-detected boolean.
    """

    if active_low:
        return not raw_signal

    return raw_signal


class SimulatedMetalSensorBackend:
    """
    Safe simulated backend for tests.

    Does not touch GPIO.
    """

    def __init__(
        self,
        fixed_signal: bool = False,
        sequence: list[bool] | tuple[bool, ...] | None = None,
    ) -> None:
        self.fixed_signal = bool(fixed_signal)
        self.sequence = list(sequence or [])
        self._index = 0

    def read_signal(self, config: MetalSensorConfig) -> bool:
        if self.sequence:
            value = bool(self.sequence[self._index % len(self.sequence)])
            self._index += 1
            return value

        return self.fixed_signal


class GpioZeroMetalSensorBackend:
    """
    Real GPIO backend using gpiozero.DigitalInputDevice.

    Use only after Omron sensor signal is safely interfaced to Raspberry Pi GPIO.

    Install if missing:
        sudo apt install -y python3-gpiozero
    """

    def __init__(self, pull_up: bool | None = None) -> None:
        try:
            from gpiozero import DigitalInputDevice
        except ImportError as exc:
            raise MetalSensorError(
                "gpiozero is required for real metal sensor reads. "
                "Install with: sudo apt install -y python3-gpiozero"
            ) from exc

        self._input_class = DigitalInputDevice
        self.pull_up = pull_up
        self._devices: dict[int, Any] = {}

    def _get_device(self, config: MetalSensorConfig):
        if config.signal_gpio not in self._devices:
            self._devices[config.signal_gpio] = self._input_class(
                pin=config.signal_gpio,
                pull_up=self.pull_up,
            )

        return self._devices[config.signal_gpio]

    def read_signal(self, config: MetalSensorConfig) -> bool:
        device = self._get_device(config)
        return bool(device.value)

    def close(self) -> None:
        for device in self._devices.values():
            if hasattr(device, "close"):
                device.close()

        self._devices.clear()


class MetalSensor:
    """
    Production wrapper for Omron metal sensor input.
    """

    def __init__(
        self,
        config: MetalSensorConfig,
        backend: MetalSensorBackend | None = None,
    ) -> None:
        _validate_config(config)

        self.config = config
        self.backend = backend or SimulatedMetalSensorBackend()

    def read_once(self) -> MetalSensorReading:
        """
        Read one raw sensor sample and convert it to metalDetected.
        """

        if not self.config.enabled:
            return MetalSensorReading(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                metalDetected=None,
                rawValues=[],
                valid=False,
                faultCode="metal_sensor_not_enabled",
                message="Metal sensor is not enabled in configuration.",
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
            )

        try:
            raw_signal = bool(self.backend.read_signal(self.config))
            metal_detected = _raw_to_metal_detected(
                raw_signal=raw_signal,
                active_low=self.config.active_low,
            )

            return MetalSensorReading(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                metalDetected=metal_detected,
                rawValues=[raw_signal],
                valid=True,
                faultCode=None,
                message="Metal sensor reading is valid.",
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
            )

        except Exception as exc:
            logger.warning("Metal sensor read failed: %s", exc)

            return MetalSensorReading(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                metalDetected=None,
                rawValues=[],
                valid=False,
                faultCode="metal_sensor_read_failed",
                message=str(exc),
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
            )

    def read_debounced(self) -> MetalSensorReading:
        """
        Read multiple samples and return majority-voted metal detection.

        This reduces false flicker/noise from raw digital input.
        """

        if not self.config.enabled:
            return self.read_once()

        raw_values: list[bool] = []
        detected_values: list[bool] = []
        fault_codes: list[str] = []

        for index in range(self.config.samples):
            reading = self.read_once()

            raw_values.extend(reading.rawValues)

            if reading.valid and reading.metalDetected is not None:
                detected_values.append(bool(reading.metalDetected))
            elif reading.faultCode:
                fault_codes.append(reading.faultCode)

            if index < self.config.samples - 1 and self.config.sample_delay_seconds > 0:
                time.sleep(self.config.sample_delay_seconds)

        if not detected_values:
            fault_code = (
                "metal_sensor_no_valid_samples"
                if not fault_codes
                else f"metal_sensor_no_valid_samples:{','.join(sorted(set(fault_codes)))}"
            )

            return MetalSensorReading(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                metalDetected=None,
                rawValues=raw_values,
                valid=False,
                faultCode=fault_code,
                message="No valid metal sensor samples were collected.",
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
            )

        true_count = sum(1 for value in detected_values if value)
        false_count = len(detected_values) - true_count
        metal_detected = true_count >= false_count

        return MetalSensorReading(
            sensorName=self.config.name,
            timestamp=_now_iso(),
            metalDetected=metal_detected,
            rawValues=raw_values,
            valid=True,
            faultCode=None,
            message="Debounced metal sensor reading is valid.",
            signalGpio=self.config.signal_gpio,
            activeLow=self.config.active_low,
        )

    def check_signal_health(
        self,
        samples: int = 20,
        sample_delay_seconds: float = 0.02,
    ) -> MetalSensorHealth:
        """
        Check whether sensor signal appears stuck HIGH or stuck LOW.

        Note:
            A stuck HIGH/LOW result is not always proof of sensor failure if a
            metal object is permanently present during the test.
        """

        if samples <= 0:
            raise MetalSensorError("health check samples must be greater than zero")

        if sample_delay_seconds < 0:
            raise MetalSensorError("health check sample_delay_seconds cannot be negative")

        if not self.config.enabled:
            return MetalSensorHealth(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                ok=False,
                status="not_configured",
                faultCode="metal_sensor_not_enabled",
                message="Metal sensor is not enabled in configuration.",
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
                samplesChecked=0,
                highCount=0,
                lowCount=0,
            )

        raw_values: list[bool] = []

        for index in range(samples):
            try:
                raw_values.append(bool(self.backend.read_signal(self.config)))
            except Exception as exc:
                return MetalSensorHealth(
                    sensorName=self.config.name,
                    timestamp=_now_iso(),
                    ok=False,
                    status="critical",
                    faultCode="metal_sensor_health_read_failed",
                    message=str(exc),
                    signalGpio=self.config.signal_gpio,
                    activeLow=self.config.active_low,
                    samplesChecked=len(raw_values),
                    highCount=sum(1 for value in raw_values if value),
                    lowCount=sum(1 for value in raw_values if not value),
                )

            if index < samples - 1 and sample_delay_seconds > 0:
                time.sleep(sample_delay_seconds)

        high_count = sum(1 for value in raw_values if value)
        low_count = samples - high_count

        if high_count == samples:
            return MetalSensorHealth(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                ok=False,
                status="warning",
                faultCode="metal_sensor_signal_stuck_high",
                message="Metal sensor raw signal stayed HIGH for all samples.",
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
                samplesChecked=samples,
                highCount=high_count,
                lowCount=low_count,
            )

        if low_count == samples:
            return MetalSensorHealth(
                sensorName=self.config.name,
                timestamp=_now_iso(),
                ok=False,
                status="warning",
                faultCode="metal_sensor_signal_stuck_low",
                message="Metal sensor raw signal stayed LOW for all samples.",
                signalGpio=self.config.signal_gpio,
                activeLow=self.config.active_low,
                samplesChecked=samples,
                highCount=high_count,
                lowCount=low_count,
            )

        return MetalSensorHealth(
            sensorName=self.config.name,
            timestamp=_now_iso(),
            ok=True,
            status="ok",
            faultCode=None,
            message="Metal sensor signal changed during health check.",
            signalGpio=self.config.signal_gpio,
            activeLow=self.config.active_low,
            samplesChecked=samples,
            highCount=high_count,
            lowCount=low_count,
        )


def build_metal_sensor_from_pin_config(
    pin_config: MetalSensorPins,
    *,
    enabled: bool | None = None,
    backend: MetalSensorBackend | None = None,
    samples: int = 5,
) -> MetalSensor:
    """
    Build MetalSensor from central pin map config.
    """

    config = MetalSensorConfig.from_pin_config(
        pin_config,
        enabled=enabled,
        samples=samples,
    )

    return MetalSensor(
        config=config,
        backend=backend,
    )


__all__ = [
    "MetalSensorError",
    "MetalSensorConfig",
    "MetalSensorReading",
    "MetalSensorHealth",
    "MetalSensorBackend",
    "SimulatedMetalSensorBackend",
    "GpioZeroMetalSensorBackend",
    "MetalSensor",
    "build_metal_sensor_from_pin_config",
]
