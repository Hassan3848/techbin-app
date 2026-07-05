"""
TechBin real dustbin capacity calibration.

Purpose:
    Store real-world calibrated empty/full distances for left and right
    compartments after sensors are mounted inside the actual dustbin.

Important:
    Empty distance is NOT the same for both compartments because sensor angle,
    mounting position, and internal compartment geometry can be different.

Current real empty readings:
    left  empty ≈ 37.70 cm
    right empty ≈ 38.90 cm

Current temporary full distance:
    5.00 cm

We will update full distance later after testing the real physical full level.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.sensors.fill_level import FillLevelConfig


@dataclass(frozen=True)
class TechBinCapacityCalibration:
    left_empty_distance_cm: float = 38.21
    right_empty_distance_cm: float = 39.00

    left_full_distance_cm: float = 5.00
    right_full_distance_cm: float = 5.00

    low_threshold_percent: float = 40.0
    full_threshold_percent: float = 80.0

    # Ignore tiny HC-SR04 variation around an empty bin.
    empty_deadband_percent: float = 3.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TECHBIN_CAPACITY_CALIBRATION = TechBinCapacityCalibration()


def techbin_left_fill_config() -> FillLevelConfig:
    calibration = TECHBIN_CAPACITY_CALIBRATION

    return FillLevelConfig(
        compartment_name="left_compartment",
        empty_distance_cm=calibration.left_empty_distance_cm,
        full_distance_cm=calibration.left_full_distance_cm,
        low_threshold_percent=calibration.low_threshold_percent,
        full_threshold_percent=calibration.full_threshold_percent,
        empty_deadband_percent=calibration.empty_deadband_percent,
    )


def techbin_right_fill_config() -> FillLevelConfig:
    calibration = TECHBIN_CAPACITY_CALIBRATION

    return FillLevelConfig(
        compartment_name="right_compartment",
        empty_distance_cm=calibration.right_empty_distance_cm,
        full_distance_cm=calibration.right_full_distance_cm,
        low_threshold_percent=calibration.low_threshold_percent,
        full_threshold_percent=calibration.full_threshold_percent,
        empty_deadband_percent=calibration.empty_deadband_percent,
    )


def get_techbin_capacity_calibration() -> TechBinCapacityCalibration:
    return TECHBIN_CAPACITY_CALIBRATION


__all__ = [
    "TechBinCapacityCalibration",
    "TECHBIN_CAPACITY_CALIBRATION",
    "techbin_left_fill_config",
    "techbin_right_fill_config",
    "get_techbin_capacity_calibration",
]
