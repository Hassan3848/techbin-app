"""
TechBin dual-compartment capacity monitor.

Purpose:
    Monitor left and right compartment fill levels and update their capacity
    traffic light indicators.

Final hardware meaning:
    left compartment:
        left ultrasonic sensor -> left fill level -> left traffic light

    right compartment:
        right ultrasonic sensor -> right fill level -> right traffic light

Traffic light meaning:
    green  -> low fill / enough space
    yellow -> medium or half fill
    red    -> high/full compartment
    off    -> unknown, disabled, or invalid reading

Safety:
    This module does not require real GPIO by itself.
    Real GPIO is only used if ultrasonic/indicator backends are configured for it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import time
from typing import Any

from app.logger import get_logger
from app.sensors.capacity_indicator import CapacityIndicator, CapacityIndicatorState
from app.sensors.capacity_calibration import (
    techbin_left_fill_config,
    techbin_right_fill_config,
)
from app.sensors.fill_level import (
    FillLevelConfig,
    FillLevelResult,
    estimate_fill_level_from_ultrasonic,
)
from app.sensors.ultrasonic import UltrasonicDistanceSensor, UltrasonicReading


logger = get_logger(__name__)


class CapacityMonitorError(RuntimeError):
    """Raised when capacity monitoring fails."""


@dataclass(frozen=True)
class CompartmentCapacityResult:
    """
    Full capacity result for one compartment.
    """

    compartmentName: str
    timestamp: str
    ultrasonicReading: dict[str, Any]
    fillLevel: dict[str, Any]
    indicatorState: dict[str, Any] | None
    valid: bool
    faultCode: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DualCapacityMonitorResult:
    """
    Full capacity result for both compartments.
    """

    timestamp: str
    left: dict[str, Any]
    right: dict[str, Any]
    overallValid: bool
    faultCodes: list[str]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


class CompartmentCapacityMonitor:
    """
    Monitor one compartment using:
        ultrasonic sensor
        fill-level config
        optional traffic light indicator
    """

    def __init__(
        self,
        *,
        compartment_name: str,
        ultrasonic_sensor: UltrasonicDistanceSensor,
        fill_config: FillLevelConfig,
        indicator: CapacityIndicator | None = None,
        update_indicator: bool = True,
    ) -> None:
        if not compartment_name.strip():
            raise CapacityMonitorError("compartment_name cannot be empty")

        self.compartment_name = compartment_name.strip()
        self.ultrasonic_sensor = ultrasonic_sensor
        self.fill_config = fill_config
        self.indicator = indicator
        self.update_indicator = update_indicator

    def check_capacity(self) -> CompartmentCapacityResult:
        """
        Read ultrasonic distance, estimate fill level, and update indicator.
        """

        try:
            ultrasonic_reading: UltrasonicReading = self.ultrasonic_sensor.read_filtered()

            fill_result: FillLevelResult = estimate_fill_level_from_ultrasonic(
                reading=ultrasonic_reading,
                config=self.fill_config,
            )

            indicator_state: CapacityIndicatorState | None = None

            if self.update_indicator and self.indicator is not None:
                indicator_state = self.indicator.apply_fill_level(fill_result)

            valid = fill_result.valid
            fault_code = fill_result.faultCode

            if indicator_state is not None and not indicator_state.valid:
                valid = False

                if fault_code:
                    fault_code = f"{fault_code};{indicator_state.faultCode}"
                else:
                    fault_code = indicator_state.faultCode

            if valid:
                message = "Compartment capacity check completed successfully."
            else:
                message = "Compartment capacity check completed with fault."

            result = CompartmentCapacityResult(
                compartmentName=self.compartment_name,
                timestamp=_now_iso(),
                ultrasonicReading=ultrasonic_reading.to_dict(),
                fillLevel=fill_result.to_dict(),
                indicatorState=(
                    indicator_state.to_dict()
                    if indicator_state is not None
                    else None
                ),
                valid=valid,
                faultCode=fault_code,
                message=message,
            )

            logger.info(
                "Capacity check | compartment=%s | valid=%s | fill=%s | level=%s | color=%s",
                self.compartment_name,
                result.valid,
                fill_result.fillPercentage,
                fill_result.capacityLevel,
                fill_result.indicatorColor,
            )

            return result

        except Exception as exc:
            logger.warning(
                "Capacity monitor failed | compartment=%s | error=%s",
                self.compartment_name,
                exc,
            )

            return CompartmentCapacityResult(
                compartmentName=self.compartment_name,
                timestamp=_now_iso(),
                ultrasonicReading={},
                fillLevel={},
                indicatorState=None,
                valid=False,
                faultCode="capacity_monitor_failed",
                message=str(exc),
            )


class DualCapacityMonitor:
    """
    Monitor both TechBin compartments.

    left:
        left ultrasonic + left fill config + left traffic light

    right:
        right ultrasonic + right fill config + right traffic light
    """

    def __init__(
        self,
        *,
        left_monitor: CompartmentCapacityMonitor,
        right_monitor: CompartmentCapacityMonitor,
        inter_sensor_delay_seconds: float = 0.25,
    ) -> None:
        if inter_sensor_delay_seconds < 0:
            raise CapacityMonitorError(
                "inter_sensor_delay_seconds cannot be negative"
            )

        self.left_monitor = left_monitor
        self.right_monitor = right_monitor
        self.inter_sensor_delay_seconds = float(inter_sensor_delay_seconds)

    def check_all(self) -> DualCapacityMonitorResult:
        """
        Run both left and right capacity checks.
        """

        left_result = self.left_monitor.check_capacity()

        # Do not trigger left/right HC-SR04 sensors at the same instant.
        time.sleep(self.inter_sensor_delay_seconds)

        right_result = self.right_monitor.check_capacity()

        fault_codes: list[str] = []

        if left_result.faultCode:
            fault_codes.append(f"left:{left_result.faultCode}")

        if right_result.faultCode:
            fault_codes.append(f"right:{right_result.faultCode}")

        overall_valid = left_result.valid and right_result.valid

        if overall_valid:
            message = "Both compartment capacity checks completed successfully."
        else:
            message = "One or more compartment capacity checks reported a fault."

        result = DualCapacityMonitorResult(
            timestamp=_now_iso(),
            left=left_result.to_dict(),
            right=right_result.to_dict(),
            overallValid=overall_valid,
            faultCodes=fault_codes,
            message=message,
        )

        logger.info(
            "Dual capacity check | overall_valid=%s | faults=%s",
            overall_valid,
            fault_codes,
        )

        return result


def build_default_left_capacity_monitor(
    *,
    ultrasonic_sensor: UltrasonicDistanceSensor,
    indicator: CapacityIndicator | None = None,
    fill_config: FillLevelConfig | None = None,
    update_indicator: bool = True,
) -> CompartmentCapacityMonitor:
    """
    Build left compartment capacity monitor with default calibration.

    Default calibration must be replaced after real dustbin dimensions are measured.
    """

    return CompartmentCapacityMonitor(
        compartment_name="left_compartment",
        ultrasonic_sensor=ultrasonic_sensor,
        fill_config=fill_config or techbin_left_fill_config(),
        indicator=indicator,
        update_indicator=update_indicator,
    )


def build_default_right_capacity_monitor(
    *,
    ultrasonic_sensor: UltrasonicDistanceSensor,
    indicator: CapacityIndicator | None = None,
    fill_config: FillLevelConfig | None = None,
    update_indicator: bool = True,
) -> CompartmentCapacityMonitor:
    """
    Build right compartment capacity monitor with default calibration.

    Default calibration must be replaced after real dustbin dimensions are measured.
    """

    return CompartmentCapacityMonitor(
        compartment_name="right_compartment",
        ultrasonic_sensor=ultrasonic_sensor,
        fill_config=fill_config or techbin_right_fill_config(),
        indicator=indicator,
        update_indicator=update_indicator,
    )


__all__ = [
    "CapacityMonitorError",
    "CompartmentCapacityResult",
    "DualCapacityMonitorResult",
    "CompartmentCapacityMonitor",
    "DualCapacityMonitor",
    "build_default_left_capacity_monitor",
    "build_default_right_capacity_monitor",
]
