"""
TechBin Raspberry Pi GPIO pin map.

Important:
    This project uses BCM GPIO numbering, not physical board pin numbering.

Safety:
    - HC-SR04 Echo output is 5V and must NOT connect directly to Raspberry Pi GPIO.
    - Use resistor divider or proper level shifter for each Echo pin.
    - Omron metal sensor must not connect directly without safe interfacing/isolation.
    - LED/traffic light modules must use proper current limiting or module-safe input design.
    - Final pin choices can be changed here without changing sensor modules.

Current planned hardware:
    - 3 x HC-SR04 ultrasonic sensors
    - Omron E2E-X5ME1-Z inductive proximity sensor
    - 2 x traffic light modules for compartment capacity
    - MAX98357 speaker later
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class UltrasonicSensorPins:
    """
    Pin pair for one HC-SR04 ultrasonic sensor.
    """

    name: str
    trigger_gpio: int
    echo_gpio: int
    role: str
    enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetalSensorPins:
    """
    GPIO config for metal sensor input.

    active_low:
        False means HIGH = metal detected.
        True means LOW = metal detected.
    """

    signal_gpio: int
    enabled: bool = False
    active_low: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrafficLightPins:
    """
    GPIO pins for one traffic light indicator module.

    Usage in TechBin:
        left_capacity_indicator
        right_capacity_indicator

    active_low:
        False means GPIO HIGH turns light ON.
        True means GPIO LOW turns light ON.
    """

    name: str
    red_gpio: int
    yellow_gpio: int
    green_gpio: int
    role: str
    enabled: bool = False
    active_low: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TechBinPinMap:
    """
    Complete TechBin GPIO pin map.

    All pin numbers are BCM GPIO numbers.
    """

    ultrasonic_front: UltrasonicSensorPins
    ultrasonic_left: UltrasonicSensorPins
    ultrasonic_right: UltrasonicSensorPins
    metal_sensor: MetalSensorPins
    traffic_light_left: TrafficLightPins
    traffic_light_right: TrafficLightPins

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------
# Planned BCM GPIO allocation
# ---------------------------------------------------------------------
#
# HC-SR04 sensors:
#   front sensor  -> user/session detection
#   left sensor   -> left compartment disturbance/fill support
#   right sensor  -> right compartment disturbance/fill support
#
# Traffic light modules:
#   left traffic light  -> left compartment capacity
#   right traffic light -> right compartment capacity
#
# All hardware outputs/inputs are disabled by default until wiring is verified.
# ---------------------------------------------------------------------

PIN_MAP = TechBinPinMap(
    ultrasonic_front=UltrasonicSensorPins(
        name="front_ultrasonic",
        trigger_gpio=23,
        echo_gpio=24,
        role="user_session_detection",
        enabled=True,
    ),
    ultrasonic_left=UltrasonicSensorPins(
        name="left_ultrasonic",
        trigger_gpio=5,
        echo_gpio=6,
        role="left_compartment_detection_and_fill",
        enabled=True,
    ),
    ultrasonic_right=UltrasonicSensorPins(
        name="right_ultrasonic",
        trigger_gpio=16,
        echo_gpio=20,
        role="right_compartment_detection_and_fill",
        enabled=True,
    ),
    metal_sensor=MetalSensorPins(
        signal_gpio=21,
        enabled=False,
        active_low=False,
    ),
    traffic_light_left=TrafficLightPins(
        name="left_capacity_indicator",
        red_gpio=17,
        yellow_gpio=27,
        green_gpio=22,
        role="left_compartment_capacity",
        enabled=True,
        active_low=False,
    ),
    traffic_light_right=TrafficLightPins(
        name="right_capacity_indicator",
        red_gpio=12,
        yellow_gpio=13,
        green_gpio=26,
        role="right_compartment_capacity",
        enabled=True,
        active_low=False,
    ),
)


def get_ultrasonic_pin_configs() -> tuple[UltrasonicSensorPins, ...]:
    """
    Return all ultrasonic sensor pin configs.
    """

    return (
        PIN_MAP.ultrasonic_front,
        PIN_MAP.ultrasonic_left,
        PIN_MAP.ultrasonic_right,
    )


def get_enabled_ultrasonic_pin_configs() -> tuple[UltrasonicSensorPins, ...]:
    """
    Return only enabled ultrasonic sensor configs.
    """

    return tuple(
        config
        for config in get_ultrasonic_pin_configs()
        if config.enabled
    )


def get_traffic_light_pin_configs() -> tuple[TrafficLightPins, ...]:
    """
    Return both capacity traffic light modules.
    """

    return (
        PIN_MAP.traffic_light_left,
        PIN_MAP.traffic_light_right,
    )


def get_enabled_traffic_light_pin_configs() -> tuple[TrafficLightPins, ...]:
    """
    Return only enabled traffic light modules.
    """

    return tuple(
        config
        for config in get_traffic_light_pin_configs()
        if config.enabled
    )


def validate_pin_map(pin_map: TechBinPinMap = PIN_MAP) -> None:
    """
    Validate that GPIO pins are unique and in a reasonable BCM range.

    This does not prove physical wiring is correct.
    It only prevents accidental duplicated GPIO allocation.
    """

    used_pins = [
        pin_map.ultrasonic_front.trigger_gpio,
        pin_map.ultrasonic_front.echo_gpio,
        pin_map.ultrasonic_left.trigger_gpio,
        pin_map.ultrasonic_left.echo_gpio,
        pin_map.ultrasonic_right.trigger_gpio,
        pin_map.ultrasonic_right.echo_gpio,
        pin_map.metal_sensor.signal_gpio,
        pin_map.traffic_light_left.red_gpio,
        pin_map.traffic_light_left.yellow_gpio,
        pin_map.traffic_light_left.green_gpio,
        pin_map.traffic_light_right.red_gpio,
        pin_map.traffic_light_right.yellow_gpio,
        pin_map.traffic_light_right.green_gpio,
    ]

    duplicates = sorted(
        {pin for pin in used_pins if used_pins.count(pin) > 1}
    )

    if duplicates:
        raise ValueError(f"Duplicate GPIO pins found in pin map: {duplicates}")

    invalid = [
        pin for pin in used_pins if not isinstance(pin, int) or pin < 0 or pin > 27
    ]

    if invalid:
        raise ValueError(f"Invalid BCM GPIO pins found: {invalid}")


__all__ = [
    "UltrasonicSensorPins",
    "MetalSensorPins",
    "TrafficLightPins",
    "TechBinPinMap",
    "PIN_MAP",
    "get_ultrasonic_pin_configs",
    "get_enabled_ultrasonic_pin_configs",
    "get_traffic_light_pin_configs",
    "get_enabled_traffic_light_pin_configs",
    "validate_pin_map",
]
