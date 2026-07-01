"""
TechBin capacity traffic light indicator control.

Purpose:
    Control visual fill-level indicators for left and right compartments.

Correct TechBin meaning:
    green  -> low fill / enough capacity
    yellow -> medium or half fill
    red    -> high/full compartment
    off    -> unknown / disabled / fault

Design:
    left compartment:
        left ultrasonic sensor -> left fill level -> left traffic light

    right compartment:
        right ultrasonic sensor -> right fill level -> right traffic light

This module supports:
    - simulated backend for safe tests
    - gpiozero backend for real traffic light GPIO output later
    - structured indicator state
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from app.logger import get_logger
from app.sensors.fill_level import FillLevelResult, IndicatorColor
from app.sensors.pin_map import TrafficLightPins


logger = get_logger(__name__)


IndicatorStateName = Literal["green", "yellow", "red", "off"]


class CapacityIndicatorError(RuntimeError):
    """Raised when capacity indicator setup/control fails."""


@dataclass(frozen=True)
class CapacityIndicatorConfig:
    """
    Runtime config for one traffic light capacity indicator.
    """

    name: str
    red_gpio: int
    yellow_gpio: int
    green_gpio: int
    role: str
    enabled: bool = False
    active_low: bool = False

    @classmethod
    def from_pin_config(
        cls,
        pin_config: TrafficLightPins,
        *,
        enabled: bool | None = None,
    ) -> "CapacityIndicatorConfig":
        return cls(
            name=pin_config.name,
            red_gpio=pin_config.red_gpio,
            yellow_gpio=pin_config.yellow_gpio,
            green_gpio=pin_config.green_gpio,
            role=pin_config.role,
            enabled=pin_config.enabled if enabled is None else enabled,
            active_low=pin_config.active_low,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapacityIndicatorState:
    """
    Structured result after setting an indicator.
    """

    indicatorName: str
    role: str
    timestamp: str
    requestedColor: IndicatorStateName
    activeColor: IndicatorStateName
    valid: bool
    faultCode: str | None
    message: str
    redGpio: int
    yellowGpio: int
    greenGpio: int
    activeLow: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapacityIndicatorBackend(Protocol):
    """
    Backend interface for traffic light output.
    """

    def set_outputs(
        self,
        config: CapacityIndicatorConfig,
        *,
        red: bool,
        yellow: bool,
        green: bool,
    ) -> None:
        """
        Set raw light output states.
        """

    def close(self) -> None:
        """
        Release backend resources.
        """


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _validate_config(config: CapacityIndicatorConfig) -> None:
    if not config.name.strip():
        raise CapacityIndicatorError("Indicator name cannot be empty")

    if not config.role.strip():
        raise CapacityIndicatorError("Indicator role cannot be empty")

    pins = [config.red_gpio, config.yellow_gpio, config.green_gpio]

    if len(set(pins)) != 3:
        raise CapacityIndicatorError(
            f"{config.name}: red/yellow/green GPIO pins must be unique"
        )

    for pin in pins:
        if not isinstance(pin, int) or pin < 0 or pin > 27:
            raise CapacityIndicatorError(
                f"{config.name}: invalid BCM GPIO pin: {pin}"
            )


def _normalize_color(color: str) -> IndicatorStateName:
    normalized = color.strip().lower()

    if normalized not in ("green", "yellow", "red", "off"):
        raise CapacityIndicatorError(
            "Indicator color must be one of: green, yellow, red, off"
        )

    return normalized  # type: ignore[return-value]


def _color_to_outputs(color: IndicatorStateName) -> tuple[bool, bool, bool]:
    """
    Convert active color into raw red/yellow/green boolean outputs.
    """

    if color == "red":
        return True, False, False

    if color == "yellow":
        return False, True, False

    if color == "green":
        return False, False, True

    return False, False, False


class SimulatedCapacityIndicatorBackend:
    """
    Safe simulated backend for tests.

    Does not touch GPIO.
    Stores output state in memory.
    """

    def __init__(self) -> None:
        self.states: dict[str, dict[str, bool]] = {}

    def set_outputs(
        self,
        config: CapacityIndicatorConfig,
        *,
        red: bool,
        yellow: bool,
        green: bool,
    ) -> None:
        self.states[config.name] = {
            "red": bool(red),
            "yellow": bool(yellow),
            "green": bool(green),
        }

    def get_state(self, indicator_name: str) -> dict[str, bool]:
        return self.states.get(
            indicator_name,
            {
                "red": False,
                "yellow": False,
                "green": False,
            },
        )

    def close(self) -> None:
        self.states.clear()


class GpioZeroCapacityIndicatorBackend:
    """
    Real GPIO backend using gpiozero.LED.

    Use only after traffic light module wiring is confirmed safe.

    Install if missing:
        sudo apt install -y python3-gpiozero
    """

    def __init__(self) -> None:
        try:
            from gpiozero import LED
        except ImportError as exc:
            raise CapacityIndicatorError(
                "gpiozero is required for real traffic light control. "
                "Install with: sudo apt install -y python3-gpiozero"
            ) from exc

        self._led_class = LED
        self._devices: dict[tuple[str, str], Any] = {}

    def _get_led(self, config: CapacityIndicatorConfig, color: str, pin: int):
        key = (config.name, color)

        if key not in self._devices:
            self._devices[key] = self._led_class(
                pin=pin,
                active_high=not config.active_low,
            )

        return self._devices[key]

    def set_outputs(
        self,
        config: CapacityIndicatorConfig,
        *,
        red: bool,
        yellow: bool,
        green: bool,
    ) -> None:
        red_led = self._get_led(config, "red", config.red_gpio)
        yellow_led = self._get_led(config, "yellow", config.yellow_gpio)
        green_led = self._get_led(config, "green", config.green_gpio)

        if red:
            red_led.on()
        else:
            red_led.off()

        if yellow:
            yellow_led.on()
        else:
            yellow_led.off()

        if green:
            green_led.on()
        else:
            green_led.off()

    def close(self) -> None:
        for device in self._devices.values():
            if hasattr(device, "close"):
                device.close()

        self._devices.clear()


class CapacityIndicator:
    """
    Production wrapper for one capacity traffic light module.
    """

    def __init__(
        self,
        config: CapacityIndicatorConfig,
        backend: CapacityIndicatorBackend | None = None,
    ) -> None:
        _validate_config(config)

        self.config = config
        self.backend = backend or SimulatedCapacityIndicatorBackend()

    def set_color(self, color: str) -> CapacityIndicatorState:
        """
        Set indicator to green/yellow/red/off.
        """

        requested_color = _normalize_color(color)

        if not self.config.enabled:
            return CapacityIndicatorState(
                indicatorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                requestedColor=requested_color,
                activeColor="off",
                valid=False,
                faultCode="capacity_indicator_not_enabled",
                message="Capacity indicator is not enabled in configuration.",
                redGpio=self.config.red_gpio,
                yellowGpio=self.config.yellow_gpio,
                greenGpio=self.config.green_gpio,
                activeLow=self.config.active_low,
            )

        try:
            red, yellow, green = _color_to_outputs(requested_color)

            self.backend.set_outputs(
                self.config,
                red=red,
                yellow=yellow,
                green=green,
            )

            return CapacityIndicatorState(
                indicatorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                requestedColor=requested_color,
                activeColor=requested_color,
                valid=True,
                faultCode=None,
                message=f"Capacity indicator set to {requested_color}.",
                redGpio=self.config.red_gpio,
                yellowGpio=self.config.yellow_gpio,
                greenGpio=self.config.green_gpio,
                activeLow=self.config.active_low,
            )

        except Exception as exc:
            logger.warning(
                "Capacity indicator control failed | indicator=%s | error=%s",
                self.config.name,
                exc,
            )

            return CapacityIndicatorState(
                indicatorName=self.config.name,
                role=self.config.role,
                timestamp=_now_iso(),
                requestedColor=requested_color,
                activeColor="off",
                valid=False,
                faultCode="capacity_indicator_set_failed",
                message=str(exc),
                redGpio=self.config.red_gpio,
                yellowGpio=self.config.yellow_gpio,
                greenGpio=self.config.green_gpio,
                activeLow=self.config.active_low,
            )

    def apply_fill_level(self, fill_result: FillLevelResult) -> CapacityIndicatorState:
        """
        Set indicator based on fill-level result.
        """

        color: IndicatorColor = fill_result.indicatorColor
        return self.set_color(color)

    def off(self) -> CapacityIndicatorState:
        """
        Turn all lights off.
        """

        return self.set_color("off")

    def close(self) -> None:
        self.backend.close()


@dataclass
class DualCapacityIndicators:
    """
    Wrapper for left and right compartment capacity indicators.
    """

    left: CapacityIndicator
    right: CapacityIndicator

    def apply(
        self,
        *,
        left_fill: FillLevelResult,
        right_fill: FillLevelResult,
    ) -> dict[str, dict[str, Any]]:
        """
        Apply left and right fill-level results to both traffic light modules.
        """

        left_state = self.left.apply_fill_level(left_fill)
        right_state = self.right.apply_fill_level(right_fill)

        return {
            "left": left_state.to_dict(),
            "right": right_state.to_dict(),
        }

    def off(self) -> dict[str, dict[str, Any]]:
        """
        Turn both indicators off.
        """

        return {
            "left": self.left.off().to_dict(),
            "right": self.right.off().to_dict(),
        }

    def close(self) -> None:
        self.left.close()
        self.right.close()


def build_indicator_from_pin_config(
    pin_config: TrafficLightPins,
    *,
    enabled: bool | None = None,
    backend: CapacityIndicatorBackend | None = None,
) -> CapacityIndicator:
    """
    Build CapacityIndicator from central pin map config.
    """

    config = CapacityIndicatorConfig.from_pin_config(
        pin_config,
        enabled=enabled,
    )

    return CapacityIndicator(
        config=config,
        backend=backend,
    )


def build_dual_capacity_indicators(
    *,
    left_pin_config: TrafficLightPins,
    right_pin_config: TrafficLightPins,
    enabled: bool | None = None,
    backend: CapacityIndicatorBackend | None = None,
) -> DualCapacityIndicators:
    """
    Build left and right capacity indicators.

    If one shared backend is provided, both indicators use it.
    """

    active_backend = backend or SimulatedCapacityIndicatorBackend()

    return DualCapacityIndicators(
        left=build_indicator_from_pin_config(
            left_pin_config,
            enabled=enabled,
            backend=active_backend,
        ),
        right=build_indicator_from_pin_config(
            right_pin_config,
            enabled=enabled,
            backend=active_backend,
        ),
    )


__all__ = [
    "IndicatorStateName",
    "CapacityIndicatorError",
    "CapacityIndicatorConfig",
    "CapacityIndicatorState",
    "CapacityIndicatorBackend",
    "SimulatedCapacityIndicatorBackend",
    "GpioZeroCapacityIndicatorBackend",
    "CapacityIndicator",
    "DualCapacityIndicators",
    "build_indicator_from_pin_config",
    "build_dual_capacity_indicators",
]
