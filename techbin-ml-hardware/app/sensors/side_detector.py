"""
TechBin left/right compartment side detector.

Purpose:
    Detect which compartment was used during a disposal session by comparing
    left and right ultrasonic distance changes.

Important:
    This is NOT fill-level monitoring.
    Fill-level monitoring estimates capacity over time.
    Side detection looks for a short-term disturbance/change during a disposal event.

Final product logic:
    left compartment  -> non-recyclable/trash
    right compartment -> recyclable

Rules:
    - left disturbance only  -> disposalSide = left
    - right disturbance only -> disposalSide = right
    - no disturbance         -> unknown / reject event if required
    - both disturbed         -> ambiguous unless one side clearly dominates
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import time
from typing import Any, Literal

from app.config import LEFT_SIDE, RIGHT_SIDE
from app.logger import get_logger
from app.sensors.ultrasonic import UltrasonicDistanceSensor, UltrasonicReading


logger = get_logger(__name__)


DetectedSide = Literal["left", "right", "unknown", "ambiguous"]


class SideDetectionError(RuntimeError):
    """Raised when side detection cannot be completed."""


@dataclass(frozen=True)
class SideDetectionConfig:
    """
    Configuration for compartment side detection.

    disturbance_threshold_cm:
        Minimum distance change required to treat a compartment as disturbed.

    dominance_margin_cm:
        If both compartments are disturbed, one side must exceed the other by
        at least this margin to be selected. Otherwise result is ambiguous.

    use_absolute_delta:
        False:
            delta = baseline - current
            This assumes object/waste becomes closer to the top-mounted sensor.

        True:
            delta = absolute distance change
            Useful during early testing if sensor geometry is not finalized.
    """

    disturbance_threshold_cm: float = 5.0
    dominance_margin_cm: float = 6.0
    use_absolute_delta: bool = False

    # Delay between left/right reads prevents ultrasonic echo cross-talk.
    inter_sensor_delay_seconds: float = 0.25

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompartmentSideEvidence:
    """
    Side evidence for one compartment.
    """

    side: str
    baselineDistanceCm: float | None
    currentDistanceCm: float | None
    deltaCm: float | None
    disturbed: bool
    valid: bool
    faultCode: str | None
    message: str
    baselineReading: dict[str, Any] | None
    currentReading: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SideDetectionResult:
    """
    Result of left/right side detection.
    """

    timestamp: str
    detectedSide: DetectedSide
    disposalSide: str | None
    leftEvidence: dict[str, Any]
    rightEvidence: dict[str, Any]
    valid: bool
    faultCode: str | None
    message: str
    warnings: list[str]
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _validate_config(config: SideDetectionConfig) -> None:
    if config.disturbance_threshold_cm <= 0:
        raise SideDetectionError("disturbance_threshold_cm must be positive")

    if config.dominance_margin_cm < 0:
        raise SideDetectionError("dominance_margin_cm cannot be negative")

    if config.inter_sensor_delay_seconds < 0:
        raise SideDetectionError(
            "inter_sensor_delay_seconds cannot be negative"
        )


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None

    return round(float(value), 2)


def _extract_distance(reading: UltrasonicReading | None) -> float | None:
    if reading is None:
        return None

    if not reading.valid:
        return None

    if reading.distanceCm is None:
        return None

    return float(reading.distanceCm)


def build_compartment_evidence(
    *,
    side: str,
    baseline_reading: UltrasonicReading | None,
    current_reading: UltrasonicReading | None,
    config: SideDetectionConfig,
) -> CompartmentSideEvidence:
    """
    Build disturbance evidence for one compartment.
    """

    _validate_config(config)

    baseline_distance = _extract_distance(baseline_reading)
    current_distance = _extract_distance(current_reading)

    if baseline_reading is None:
        return CompartmentSideEvidence(
            side=side,
            baselineDistanceCm=None,
            currentDistanceCm=_round_or_none(current_distance),
            deltaCm=None,
            disturbed=False,
            valid=False,
            faultCode="baseline_reading_missing",
            message="Baseline reading is missing.",
            baselineReading=None,
            currentReading=current_reading.to_dict() if current_reading else None,
        )

    if current_reading is None:
        return CompartmentSideEvidence(
            side=side,
            baselineDistanceCm=_round_or_none(baseline_distance),
            currentDistanceCm=None,
            deltaCm=None,
            disturbed=False,
            valid=False,
            faultCode="current_reading_missing",
            message="Current reading is missing.",
            baselineReading=baseline_reading.to_dict(),
            currentReading=None,
        )

    if not baseline_reading.valid:
        return CompartmentSideEvidence(
            side=side,
            baselineDistanceCm=None,
            currentDistanceCm=_round_or_none(current_distance),
            deltaCm=None,
            disturbed=False,
            valid=False,
            faultCode=baseline_reading.faultCode or "baseline_reading_invalid",
            message=f"Baseline reading is invalid: {baseline_reading.message}",
            baselineReading=baseline_reading.to_dict(),
            currentReading=current_reading.to_dict(),
        )

    if not current_reading.valid:
        return CompartmentSideEvidence(
            side=side,
            baselineDistanceCm=_round_or_none(baseline_distance),
            currentDistanceCm=None,
            deltaCm=None,
            disturbed=False,
            valid=False,
            faultCode=current_reading.faultCode or "current_reading_invalid",
            message=f"Current reading is invalid: {current_reading.message}",
            baselineReading=baseline_reading.to_dict(),
            currentReading=current_reading.to_dict(),
        )

    if baseline_distance is None or current_distance is None:
        return CompartmentSideEvidence(
            side=side,
            baselineDistanceCm=_round_or_none(baseline_distance),
            currentDistanceCm=_round_or_none(current_distance),
            deltaCm=None,
            disturbed=False,
            valid=False,
            faultCode="distance_missing",
            message="Distance value is missing.",
            baselineReading=baseline_reading.to_dict(),
            currentReading=current_reading.to_dict(),
        )

    raw_delta = baseline_distance - current_distance

    if config.use_absolute_delta:
        delta = abs(raw_delta)
    else:
        delta = raw_delta

    disturbed = delta >= config.disturbance_threshold_cm

    return CompartmentSideEvidence(
        side=side,
        baselineDistanceCm=round(baseline_distance, 2),
        currentDistanceCm=round(current_distance, 2),
        deltaCm=round(delta, 2),
        disturbed=disturbed,
        valid=True,
        faultCode=None,
        message="Compartment side evidence is valid.",
        baselineReading=baseline_reading.to_dict(),
        currentReading=current_reading.to_dict(),
    )


def detect_side_from_evidence(
    *,
    left_evidence: CompartmentSideEvidence,
    right_evidence: CompartmentSideEvidence,
    config: SideDetectionConfig,
) -> SideDetectionResult:
    """
    Decide disposal side from left/right compartment evidence.
    """

    _validate_config(config)

    warnings: list[str] = []

    left_valid = left_evidence.valid
    right_valid = right_evidence.valid

    if not left_valid or not right_valid:
        fault_codes = []

        if left_evidence.faultCode:
            fault_codes.append(f"left:{left_evidence.faultCode}")

        if right_evidence.faultCode:
            fault_codes.append(f"right:{right_evidence.faultCode}")

        return SideDetectionResult(
            timestamp=_now_iso(),
            detectedSide="unknown",
            disposalSide=None,
            leftEvidence=left_evidence.to_dict(),
            rightEvidence=right_evidence.to_dict(),
            valid=False,
            faultCode="side_evidence_invalid",
            message="Cannot detect disposal side because one or both side readings are invalid.",
            warnings=fault_codes,
            config=config.to_dict(),
        )

    left_disturbed = left_evidence.disturbed
    right_disturbed = right_evidence.disturbed

    left_delta = left_evidence.deltaCm or 0.0
    right_delta = right_evidence.deltaCm or 0.0

    if left_disturbed and not right_disturbed:
        return SideDetectionResult(
            timestamp=_now_iso(),
            detectedSide="left",
            disposalSide=LEFT_SIDE,
            leftEvidence=left_evidence.to_dict(),
            rightEvidence=right_evidence.to_dict(),
            valid=True,
            faultCode=None,
            message="Left compartment disturbance detected.",
            warnings=warnings,
            config=config.to_dict(),
        )

    if right_disturbed and not left_disturbed:
        return SideDetectionResult(
            timestamp=_now_iso(),
            detectedSide="right",
            disposalSide=RIGHT_SIDE,
            leftEvidence=left_evidence.to_dict(),
            rightEvidence=right_evidence.to_dict(),
            valid=True,
            faultCode=None,
            message="Right compartment disturbance detected.",
            warnings=warnings,
            config=config.to_dict(),
        )

    if not left_disturbed and not right_disturbed:
        return SideDetectionResult(
            timestamp=_now_iso(),
            detectedSide="unknown",
            disposalSide=None,
            leftEvidence=left_evidence.to_dict(),
            rightEvidence=right_evidence.to_dict(),
            valid=False,
            faultCode="no_compartment_disturbance",
            message="No clear compartment disturbance was detected.",
            warnings=warnings,
            config=config.to_dict(),
        )

    delta_difference = abs(left_delta - right_delta)

    if delta_difference < config.dominance_margin_cm:
        return SideDetectionResult(
            timestamp=_now_iso(),
            detectedSide="ambiguous",
            disposalSide=None,
            leftEvidence=left_evidence.to_dict(),
            rightEvidence=right_evidence.to_dict(),
            valid=False,
            faultCode="ambiguous_compartment_disturbance",
            message="Both compartments were disturbed and neither side clearly dominated.",
            warnings=[
                f"left_delta_cm={left_delta}",
                f"right_delta_cm={right_delta}",
                f"dominance_margin_cm={config.dominance_margin_cm}",
            ],
            config=config.to_dict(),
        )

    if left_delta > right_delta:
        warnings.append("both_compartments_disturbed_but_left_dominated")

        return SideDetectionResult(
            timestamp=_now_iso(),
            detectedSide="left",
            disposalSide=LEFT_SIDE,
            leftEvidence=left_evidence.to_dict(),
            rightEvidence=right_evidence.to_dict(),
            valid=True,
            faultCode=None,
            message="Both compartments disturbed, but left side clearly dominated.",
            warnings=warnings,
            config=config.to_dict(),
        )

    warnings.append("both_compartments_disturbed_but_right_dominated")

    return SideDetectionResult(
        timestamp=_now_iso(),
        detectedSide="right",
        disposalSide=RIGHT_SIDE,
        leftEvidence=left_evidence.to_dict(),
        rightEvidence=right_evidence.to_dict(),
        valid=True,
        faultCode=None,
        message="Both compartments disturbed, but right side clearly dominated.",
        warnings=warnings,
        config=config.to_dict(),
    )


def detect_side_from_readings(
    *,
    left_baseline: UltrasonicReading,
    left_current: UltrasonicReading,
    right_baseline: UltrasonicReading,
    right_current: UltrasonicReading,
    config: SideDetectionConfig | None = None,
) -> SideDetectionResult:
    """
    Decide disposal side directly from four ultrasonic readings.
    """

    active_config = config or SideDetectionConfig()

    left_evidence = build_compartment_evidence(
        side=LEFT_SIDE,
        baseline_reading=left_baseline,
        current_reading=left_current,
        config=active_config,
    )

    right_evidence = build_compartment_evidence(
        side=RIGHT_SIDE,
        baseline_reading=right_baseline,
        current_reading=right_current,
        config=active_config,
    )

    return detect_side_from_evidence(
        left_evidence=left_evidence,
        right_evidence=right_evidence,
        config=active_config,
    )


class DualUltrasonicSideDetector:
    """
    Stateful side detector using left and right ultrasonic sensors.

    Usage:
        detector.capture_baseline()
        ...
        result = detector.detect_once()

    Baseline should be captured before or at the start of a disposal session.
    Current reading should be captured when disposal activity is expected.
    """

    def __init__(
        self,
        *,
        left_sensor: UltrasonicDistanceSensor,
        right_sensor: UltrasonicDistanceSensor,
        config: SideDetectionConfig | None = None,
    ) -> None:
        self.left_sensor = left_sensor
        self.right_sensor = right_sensor
        self.config = config or SideDetectionConfig()
        _validate_config(self.config)

        self.left_baseline: UltrasonicReading | None = None
        self.right_baseline: UltrasonicReading | None = None

    def capture_baseline(self) -> tuple[UltrasonicReading, UltrasonicReading]:
        """
        Capture baseline readings for both compartments.
        """

        self.left_baseline = self.left_sensor.read_filtered()
        time.sleep(self.config.inter_sensor_delay_seconds)
        self.right_baseline = self.right_sensor.read_filtered()

        logger.info(
            "Side detector baseline captured | left=%s | right=%s",
            self.left_baseline.distanceCm,
            self.right_baseline.distanceCm,
        )

        return self.left_baseline, self.right_baseline

    def clear_baseline(self) -> None:
        """
        Clear stored baseline readings.
        """

        self.left_baseline = None
        self.right_baseline = None

    def detect_once(self) -> SideDetectionResult:
        """
        Detect side using stored baseline and fresh current readings.
        """

        if self.left_baseline is None or self.right_baseline is None:
            empty_left = CompartmentSideEvidence(
                side=LEFT_SIDE,
                baselineDistanceCm=None,
                currentDistanceCm=None,
                deltaCm=None,
                disturbed=False,
                valid=False,
                faultCode="baseline_not_captured",
                message="Left/right baseline has not been captured.",
                baselineReading=None,
                currentReading=None,
            )

            empty_right = CompartmentSideEvidence(
                side=RIGHT_SIDE,
                baselineDistanceCm=None,
                currentDistanceCm=None,
                deltaCm=None,
                disturbed=False,
                valid=False,
                faultCode="baseline_not_captured",
                message="Left/right baseline has not been captured.",
                baselineReading=None,
                currentReading=None,
            )

            return detect_side_from_evidence(
                left_evidence=empty_left,
                right_evidence=empty_right,
                config=self.config,
            )

        left_current = self.left_sensor.read_filtered()
        time.sleep(self.config.inter_sensor_delay_seconds)
        right_current = self.right_sensor.read_filtered()

        result = detect_side_from_readings(
            left_baseline=self.left_baseline,
            left_current=left_current,
            right_baseline=self.right_baseline,
            right_current=right_current,
            config=self.config,
        )

        logger.info(
            "Side detection result | side=%s | valid=%s | fault=%s",
            result.detectedSide,
            result.valid,
            result.faultCode,
        )

        return result


__all__ = [
    "DetectedSide",
    "SideDetectionError",
    "SideDetectionConfig",
    "CompartmentSideEvidence",
    "SideDetectionResult",
    "build_compartment_evidence",
    "detect_side_from_evidence",
    "detect_side_from_readings",
    "DualUltrasonicSideDetector",
]
