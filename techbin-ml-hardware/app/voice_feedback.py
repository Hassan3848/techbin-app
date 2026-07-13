"""
Local voice feedback abstraction for TechBin.

Voice is intentionally local-only. This module does not write playback history
or add any voice fields to cloud payloads.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import settings


CORRECT_MESSAGE = "Thank you for disposing the waste correctly."
INCORRECT_RECYCLABLE_MESSAGE = "This item belongs in the recyclable compartment. Please be careful next time."
INCORRECT_NON_RECYCLABLE_MESSAGE = "This item belongs in the non-recyclable compartment. Please be careful next time."


@dataclass(frozen=True)
class VoiceFeedbackStatus:
    status: str
    faultCode: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "faultCode": self.faultCode,
            "message": self.message,
        }


class VoiceFeedbackBackend(Protocol):
    def play(self, message_key: str, text: str) -> None:
        ...

    def health(self) -> VoiceFeedbackStatus:
        ...


class DisabledVoiceFeedbackBackend:
    def play(self, message_key: str, text: str) -> None:
        return None

    def health(self) -> VoiceFeedbackStatus:
        return VoiceFeedbackStatus(
            status="disabled",
            faultCode=None,
            message="Voice feedback is intentionally disabled.",
        )


class PrerecordedAudioBackend:
    FILE_NAMES = {
        "correct": "correct.wav",
        "incorrect_recyclable": "incorrect_recyclable.wav",
        "incorrect_non_recyclable": "incorrect_non_recyclable.wav",
    }

    def __init__(self, *, audio_dir: str, player_command: str) -> None:
        self.audio_dir = Path(audio_dir).expanduser()
        self.player_command = player_command.strip()

    def health(self) -> VoiceFeedbackStatus:
        if self.player_command == "":
            return VoiceFeedbackStatus("not_installed", "voice_player_not_configured", "Voice player command is not configured.")
        if not self.audio_dir.exists() or not self.audio_dir.is_dir():
            return VoiceFeedbackStatus("not_installed", "voice_audio_dir_missing", "Voice audio directory is missing.")

        missing = [
            name
            for name in self.FILE_NAMES.values()
            if not (self.audio_dir / name).exists()
        ]
        if missing:
            return VoiceFeedbackStatus("not_installed", "voice_audio_files_missing", "Required prerecorded audio files are missing.")

        return VoiceFeedbackStatus("healthy", None, "Prerecorded voice feedback is configured.")

    def play(self, message_key: str, text: str) -> None:
        status = self.health()
        if status.status != "healthy":
            return None

        file_name = self.FILE_NAMES.get(message_key)
        if file_name is None:
            return None

        audio_path = str(self.audio_dir / file_name)

        def worker() -> None:
            subprocess.run(
                [self.player_command, audio_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        threading.Thread(target=worker, daemon=True).start()


class VoiceFeedback:
    def __init__(self, backend: VoiceFeedbackBackend | None = None) -> None:
        self.backend = backend or build_voice_feedback_backend()

    def health(self) -> VoiceFeedbackStatus:
        return self.backend.health()

    def play_after_confirmation(self, latest_event: dict[str, Any] | None) -> bool:
        if not latest_event:
            return False
        if not latest_event.get("placementConfirmed"):
            return False
        if latest_event.get("correct") is None:
            return False
        if latest_event.get("expectedSide") not in ("recyclable", "non_recyclable"):
            return False

        correct = bool(latest_event["correct"])
        if correct:
            key = "correct"
            text = CORRECT_MESSAGE
        elif latest_event["expectedSide"] == "recyclable":
            key = "incorrect_recyclable"
            text = INCORRECT_RECYCLABLE_MESSAGE
        else:
            key = "incorrect_non_recyclable"
            text = INCORRECT_NON_RECYCLABLE_MESSAGE

        self.backend.play(key, text)
        return True


def build_voice_feedback_backend() -> VoiceFeedbackBackend:
    if not settings.voice_feedback.enabled:
        return DisabledVoiceFeedbackBackend()

    if settings.voice_feedback.backend == "prerecorded_audio":
        return PrerecordedAudioBackend(
            audio_dir=settings.voice_feedback.audio_dir,
            player_command=settings.voice_feedback.player_command,
        )

    return DisabledVoiceFeedbackBackend()


__all__ = [
    "VoiceFeedbackStatus",
    "VoiceFeedbackBackend",
    "DisabledVoiceFeedbackBackend",
    "PrerecordedAudioBackend",
    "VoiceFeedback",
    "build_voice_feedback_backend",
]
