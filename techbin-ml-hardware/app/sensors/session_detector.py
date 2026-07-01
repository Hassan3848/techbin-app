"""
TechBin front ultrasonic session detector.

Purpose:
    Detect whether a user/object is near the bin opening and whether a possible
    disposal session has started.

Important product rule:
    A front ultrasonic session trigger alone is NOT a disposal event.

A valid disposal event still needs:
    - image capture
    - ML class prediction
    - disposal side confirmation
    - confidence checks
    - event processing

This module only answers:
    "Is someone/something close enough to start a possible disposal session?"
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from app.logger import get_logger
from app.sensors.ultrasonic import UltrasonicDistanceSensor, UltrasonicReading


logger = get_logger(__name__)


SessionState = Literal[
    "idle",
    "presence_candidate",
    "active",
    "ending_candidate",
    "ended",
    "fault",
]


class SessionDetectorError(RuntimeError):
    """Raised when session detection fails unexpectedly."""


@dataclass(frozen=True)
class SessionDetectorConfig:
    """
    Configuration for front ultrasonic session detection.

    presence_threshold_cm:
        If front distance is less than or equal to this value, presence is detected.

    stable_presence_reads:
        Number of consecutive presence readings required to start/confirm session.

    stable_absence_reads:
        Number of consecutive absence readings required to end session.
    """

    name: str = "front_session_detector"
    presence_threshold_cm: float = 35.0
    stable_presence_reads: int = 2
    stable_absence_reads: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionDetectionResult:
    """
    Structured result of one session detector update.
    """

    detectorName: str
    timestamp: str
    state: SessionState
    sessionActive: bool
    sessionStarted: bool
    sessionEnded: bool
    presenceDetected: bool | None
    distanceCm: float | None
    valid: bool
    faultCode: str | None
    message: str
    consecutivePresenceReads: int
    consecutiveAbsenceReads: int
    config: dict[str, Any]
    ultrasonicReading: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _validate_config(config: SessionDetectorConfig) -> None:
    if not config.name.strip():
        raise SessionDetectorError("Session detector name cannot be empty")

    if config.presence_threshold_cm <= 0:
        raise SessionDetectorError("presence_threshold_cm must be positive")

    if config.stable_presence_reads <= 0:
        raise SessionDetectorError("stable_presence_reads must be greater than zero")

    if config.stable_absence_reads <= 0:
        raise SessionDetectorError("stable_absence_reads must be greater than zero")


class FrontSessionDetector:
    """
    Stateful front ultrasonic session detector.

    Typical use:
        detector = FrontSessionDetector(front_ultrasonic)
        result = detector.update()
    """

    def __init__(
        self,
        ultrasonic_sensor: UltrasonicDistanceSensor,
        config: SessionDetectorConfig | None = None,
    ) -> None:
        self.ultrasonic_sensor = ultrasonic_sensor
        self.config = config or SessionDetectorConfig()

        _validate_config(self.config)

        self._session_active = False
        self._consecutive_presence_reads = 0
        self._consecutive_absence_reads = 0
        self._last_state: SessionState = "idle"

    @property
    def session_active(self) -> bool:
        return self._session_active

    @property
    def consecutive_presence_reads(self) -> int:
        return self._consecutive_presence_reads

    @property
    def consecutive_absence_reads(self) -> int:
        return self._consecutive_absence_reads

    def reset(self) -> None:
        """
        Reset detector state.
        """

        self._session_active = False
        self._consecutive_presence_reads = 0
        self._consecutive_absence_reads = 0
        self._last_state = "idle"

    def update(self) -> SessionDetectionResult:
        """
        Read front ultrasonic sensor and update session state.
        """

        try:
            reading = self.ultrasonic_sensor.read_filtered()
            return self.update_from_reading(reading)

        except Exception as exc:
            logger.warning("Front session detector failed: %s", exc)

            self._last_state = "fault"

            return SessionDetectionResult(
                detectorName=self.config.name,
                timestamp=_now_iso(),
                state="fault",
                sessionActive=self._session_active,
                sessionStarted=False,
                sessionEnded=False,
                presenceDetected=None,
                distanceCm=None,
                valid=False,
                faultCode="session_detector_failed",
                message=str(exc),
                consecutivePresenceReads=self._consecutive_presence_reads,
                consecutiveAbsenceReads=self._consecutive_absence_reads,
                config=self.config.to_dict(),
                ultrasonicReading=None,
            )

    def update_from_reading(
        self,
        reading: UltrasonicReading,
    ) -> SessionDetectionResult:
        """
        Update detector state from an existing ultrasonic reading.

        This is useful for tests and future runtime orchestration.
        """

        if not reading.valid or reading.distanceCm is None:
            self._last_state = "fault"

            return SessionDetectionResult(
                detectorName=self.config.name,
                timestamp=_now_iso(),
                state="fault",
                sessionActive=self._session_active,
                sessionStarted=False,
                sessionEnded=False,
                presenceDetected=None,
                distanceCm=reading.distanceCm,
                valid=False,
                faultCode=reading.faultCode or "front_ultrasonic_invalid",
                message=f"Cannot update session detector because ultrasonic reading is invalid: {reading.message}",
                consecutivePresenceReads=self._consecutive_presence_reads,
                consecutiveAbsenceReads=self._consecutive_absence_reads,
                config=self.config.to_dict(),
                ultrasonicReading=reading.to_dict(),
            )

        distance_cm = float(reading.distanceCm)
        presence_detected = distance_cm <= self.config.presence_threshold_cm

        session_started = False
        session_ended = False

        if presence_detected:
            self._consecutive_presence_reads += 1
            self._consecutive_absence_reads = 0
        else:
            self._consecutive_absence_reads += 1
            self._consecutive_presence_reads = 0

        if not self._session_active:
            if self._consecutive_presence_reads >= self.config.stable_presence_reads:
                self._session_active = True
                session_started = True
                state: SessionState = "active"
            elif presence_detected:
                state = "presence_candidate"
            else:
                state = "idle"

        else:
            if self._consecutive_absence_reads >= self.config.stable_absence_reads:
                self._session_active = False
                session_ended = True
                state = "ended"
            elif not presence_detected:
                state = "ending_candidate"
            else:
                state = "active"

        self._last_state = state

        result = SessionDetectionResult(
            detectorName=self.config.name,
            timestamp=_now_iso(),
            state=state,
            sessionActive=self._session_active,
            sessionStarted=session_started,
            sessionEnded=session_ended,
            presenceDetected=presence_detected,
            distanceCm=round(distance_cm, 2),
            valid=True,
            faultCode=None,
            message="Session detector updated successfully.",
            consecutivePresenceReads=self._consecutive_presence_reads,
            consecutiveAbsenceReads=self._consecutive_absence_reads,
            config=self.config.to_dict(),
            ultrasonicReading=reading.to_dict(),
        )

        logger.info(
            "Front session detector | state=%s | active=%s | started=%s | ended=%s | distance=%s",
            result.state,
            result.sessionActive,
            result.sessionStarted,
            result.sessionEnded,
            result.distanceCm,
        )

        return result


__all__ = [
    "SessionState",
    "SessionDetectorError",
    "SessionDetectorConfig",
    "SessionDetectionResult",
    "FrontSessionDetector",
]
