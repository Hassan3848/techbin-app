"""
TechBin compartment fill-level estimation.

Purpose:
    Convert ultrasonic distance readings into bin capacity status.

Correct traffic light meaning:
    green  -> low fill / compartment has space
    yellow -> medium or half fill
    red    -> high/full compartment

Important:
    This module does not directly control GPIO lights.
    It only decides the capacity level and recommended indicator color.

How ultrasonic fill detection works:
    Sensor is mounted near the top of the compartment facing downward.

    Empty bin:
        distance from sensor to bottom is large.

    Filled bin:
        distance from sensor to waste surface becomes smaller.

Formula:
    fill_percentage =
        (empty_distance_cm - current_distance_cm)
        /
        (empty_distance_cm - full_distance_cm)
        * 100

Calibration required:
    empty_distance_cm = measured distance when compartment is empty
    full_distance_cm  = measured distance when compartment is considered full
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from app.logger import get_logger
from app.sensors.ultrasonic import UltrasonicReading


logger = get_logger(__name__)


CapacityLevel = Literal["low", "half", "full", "unknown"]
IndicatorColor = Literal["green", "yellow", "red", "off"]


class FillLevelError(ValueError):
    """Raised when fill-level configuration or reading is invalid."""


@dataclass(frozen=True)
class FillLevelConfig:
    """
    Fill-level calibration for one bin compartment.

    empty_distance_cm:
        Distance measured when compartment is empty.

    full_distance_cm:
        Distance measured when compartment is considered full.

    low_threshold_percent:
        Below this, capacity level is low.

    full_threshold_percent:
        At or above this, capacity level is full.

    Example:
        low < 40%
        half 40% to 79.99%
        full >= 80%
    """

    compartment_name: str
    empty_distance_cm: float
    full_distance_cm: float
    low_threshold_percent: float = 40.0
    full_threshold_percent: float = 80.0

    # Fill percentage at or below this value is treated as empty.
    empty_deadband_percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FillLevelResult:
    """
    Fill-level result for one compartment.
    """

    compartmentName: str
    timestamp: str
    distanceCm: float | None
    fillPercentage: float | None
    capacityLevel: CapacityLevel
    indicatorColor: IndicatorColor
    valid: bool
    faultCode: str | None
    message: str
    config: dict[str, Any]
    sourceReading: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _validate_config(config: FillLevelConfig) -> None:
    if not isinstance(config.compartment_name, str) or not config.compartment_name.strip():
        raise FillLevelError("compartment_name cannot be empty")

    if config.empty_distance_cm <= 0:
        raise FillLevelError("empty_distance_cm must be positive")

    if config.full_distance_cm <= 0:
        raise FillLevelError("full_distance_cm must be positive")

    if config.empty_distance_cm <= config.full_distance_cm:
        raise FillLevelError(
            "empty_distance_cm must be greater than full_distance_cm. "
            "Example: empty=45cm, full=8cm."
        )

    if config.low_threshold_percent < 0 or config.low_threshold_percent > 100:
        raise FillLevelError("low_threshold_percent must be between 0 and 100")

    if config.full_threshold_percent < 0 or config.full_threshold_percent > 100:
        raise FillLevelError("full_threshold_percent must be between 0 and 100")

    if config.low_threshold_percent >= config.full_threshold_percent:
        raise FillLevelError(
            "low_threshold_percent must be less than full_threshold_percent"
        )

    if config.empty_deadband_percent < 0 or config.empty_deadband_percent > 100:
        raise FillLevelError(
            "empty_deadband_percent must be between 0 and 100"
        )


def clamp_percentage(value: float) -> float:
    """
    Clamp value to 0-100 percentage.
    """

    return max(0.0, min(100.0, value))


def calculate_fill_percentage(
    distance_cm: float,
    config: FillLevelConfig,
) -> float:
    """
    Convert distance reading to fill percentage.
    """

    _validate_config(config)

    if distance_cm <= 0:
        raise FillLevelError("distance_cm must be positive")

    usable_depth = config.empty_distance_cm - config.full_distance_cm
    filled_depth = config.empty_distance_cm - distance_cm

    percentage = (filled_depth / usable_depth) * 100.0
    percentage = round(clamp_percentage(percentage), 2)

    if percentage <= config.empty_deadband_percent:
        return 0.0

    return percentage


def capacity_level_from_percentage(
    percentage: float,
    config: FillLevelConfig,
) -> CapacityLevel:
    """
    Convert fill percentage to low/half/full.
    """

    _validate_config(config)

    if percentage < config.low_threshold_percent:
        return "low"

    if percentage >= config.full_threshold_percent:
        return "full"

    return "half"


def indicator_color_for_capacity(level: CapacityLevel) -> IndicatorColor:
    """
    Convert capacity level to traffic light color.

    Correct TechBin meaning:
        low  -> green
        half -> yellow
        full -> red
    """

    if level == "low":
        return "green"

    if level == "half":
        return "yellow"

    if level == "full":
        return "red"

    return "off"


def estimate_fill_level_from_distance(
    distance_cm: float | None,
    config: FillLevelConfig,
    *,
    source_reading: UltrasonicReading | None = None,
) -> FillLevelResult:
    """
    Estimate fill level from a distance value.
    """

    _validate_config(config)

    if distance_cm is None:
        return FillLevelResult(
            compartmentName=config.compartment_name,
            timestamp=_now_iso(),
            distanceCm=None,
            fillPercentage=None,
            capacityLevel="unknown",
            indicatorColor="off",
            valid=False,
            faultCode="fill_distance_missing",
            message="Distance reading is missing.",
            config=config.to_dict(),
            sourceReading=source_reading.to_dict() if source_reading else None,
        )

    try:
        fill_percentage = calculate_fill_percentage(
            distance_cm=distance_cm,
            config=config,
        )

        capacity_level = capacity_level_from_percentage(
            percentage=fill_percentage,
            config=config,
        )

        indicator_color = indicator_color_for_capacity(capacity_level)

        return FillLevelResult(
            compartmentName=config.compartment_name,
            timestamp=_now_iso(),
            distanceCm=round(float(distance_cm), 2),
            fillPercentage=fill_percentage,
            capacityLevel=capacity_level,
            indicatorColor=indicator_color,
            valid=True,
            faultCode=None,
            message="Fill level estimate is valid.",
            config=config.to_dict(),
            sourceReading=source_reading.to_dict() if source_reading else None,
        )

    except Exception as exc:
        logger.warning(
            "Fill-level estimation failed | compartment=%s | error=%s",
            config.compartment_name,
            exc,
        )

        return FillLevelResult(
            compartmentName=config.compartment_name,
            timestamp=_now_iso(),
            distanceCm=distance_cm,
            fillPercentage=None,
            capacityLevel="unknown",
            indicatorColor="off",
            valid=False,
            faultCode="fill_level_estimation_failed",
            message=str(exc),
            config=config.to_dict(),
            sourceReading=source_reading.to_dict() if source_reading else None,
        )


def estimate_fill_level_from_ultrasonic(
    reading: UltrasonicReading,
    config: FillLevelConfig,
) -> FillLevelResult:
    """
    Estimate fill level directly from an UltrasonicReading.
    """

    _validate_config(config)

    if not reading.valid:
        return FillLevelResult(
            compartmentName=config.compartment_name,
            timestamp=_now_iso(),
            distanceCm=reading.distanceCm,
            fillPercentage=None,
            capacityLevel="unknown",
            indicatorColor="off",
            valid=False,
            faultCode=reading.faultCode or "ultrasonic_reading_invalid",
            message=f"Cannot estimate fill level because ultrasonic reading is invalid: {reading.message}",
            config=config.to_dict(),
            sourceReading=reading.to_dict(),
        )

    return estimate_fill_level_from_distance(
        distance_cm=reading.distanceCm,
        config=config,
        source_reading=reading,
    )


def default_left_fill_config() -> FillLevelConfig:
    """
    Temporary default config for left compartment.

    Must be calibrated after final dustbin dimensions are ready.
    """

    return FillLevelConfig(
        compartment_name="left_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=8.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )


def default_right_fill_config() -> FillLevelConfig:
    """
    Temporary default config for right compartment.

    Must be calibrated after final dustbin dimensions are ready.
    """

    return FillLevelConfig(
        compartment_name="right_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=8.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )


__all__ = [
    "CapacityLevel",
    "IndicatorColor",
    "FillLevelError",
    "FillLevelConfig",
    "FillLevelResult",
    "clamp_percentage",
    "calculate_fill_percentage",
    "capacity_level_from_percentage",
    "indicator_color_for_capacity",
    "estimate_fill_level_from_distance",
    "estimate_fill_level_from_ultrasonic",
    "default_left_fill_config",
    "default_right_fill_config",
]
