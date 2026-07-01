"""
Production camera capture service for TechBin.

This module owns Raspberry Pi camera startup, warmup, image capture,
safe shutdown, and capture metadata.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import ensure_runtime_directories, settings
from app.logger import get_logger


logger = get_logger(__name__)


class CameraCaptureError(RuntimeError):
    """Raised when the camera capture service fails."""


@dataclass(frozen=True)
class CaptureResult:
    """
    Result returned after a successful image capture.
    """

    image_path: Path
    captured_at: str
    width: int
    height: int
    file_size_bytes: int

    def __str__(self) -> str:
        """
        Return image path when printed.

        This keeps older prototype scripts readable when they do:
            print(result)
        """

        return str(self.image_path)

    def __fspath__(self) -> str:
        """
        Allow this object to work in some filesystem/path contexts.
        """

        return os.fspath(self.image_path)


class CameraCaptureService:
    """
    Production-style camera service for Raspberry Pi Camera Module.

    Usage:
        with CameraCaptureService() as camera:
            result = camera.capture_image(prefix="event")
    """

    def __init__(
        self,
        width: int | None = None,
        height: int | None = None,
        warmup_seconds: float | None = None,
        output_dir: Path | None = None,
        filename_prefix: str | None = None,
    ) -> None:
        self.width = width or settings.camera.image_width
        self.height = height or settings.camera.image_height
        self.warmup_seconds = (
            settings.camera.warmup_seconds
            if warmup_seconds is None
            else warmup_seconds
        )
        self.output_dir = output_dir or settings.captures_dir
        self.filename_prefix = filename_prefix or settings.camera.filename_prefix

        self._camera: Optional[object] = None
        self._is_started = False

    def __enter__(self) -> "CameraCaptureService":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()

    @property
    def is_started(self) -> bool:
        return self._is_started

    def start(self) -> None:
        """
        Initialize, configure, and start the Raspberry Pi camera.
        """

        if self._is_started:
            logger.debug("Camera service already started")
            return

        ensure_runtime_directories()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise CameraCaptureError(
                "Picamera2 is not installed or not available in this Python environment."
            ) from exc

        try:
            logger.info(
                "Starting camera service with resolution %sx%s",
                self.width,
                self.height,
            )

            camera = Picamera2()
            camera_config = camera.create_still_configuration(
                main={"size": (self.width, self.height)}
            )

            camera.configure(camera_config)
            camera.start()

            if self.warmup_seconds > 0:
                logger.debug(
                    "Warming up camera for %.2f seconds",
                    self.warmup_seconds,
                )
                time.sleep(self.warmup_seconds)

            self._camera = camera
            self._is_started = True

            logger.info("Camera service started successfully")

        except Exception as exc:
            self._camera = None
            self._is_started = False
            raise CameraCaptureError("Failed to start camera service") from exc

    def stop(self) -> None:
        """
        Stop and release the Raspberry Pi camera safely.
        """

        if self._camera is None:
            self._is_started = False
            return

        try:
            logger.debug("Stopping camera service")

            camera = self._camera

            if hasattr(camera, "stop"):
                camera.stop()

            if hasattr(camera, "close"):
                camera.close()

            logger.info("Camera service stopped")

        except Exception as exc:
            logger.warning("Camera service stop raised an error: %s", exc)

        finally:
            self._camera = None
            self._is_started = False

    def capture_image(
        self,
        output_path: Path | None = None,
        prefix: str | None = None,
    ) -> CaptureResult:
        """
        Capture one still image.

        If output_path is not provided, a timestamped filename is created
        inside the captures directory.

        The optional prefix argument keeps compatibility with older tests:
            camera.capture_image(prefix="service_test")
        """

        if not self._is_started or self._camera is None:
            raise CameraCaptureError(
                "Camera service is not started. Use start() or a context manager first."
            )

        final_output_path = output_path or self._build_output_path(prefix=prefix)
        final_output_path = final_output_path.resolve()
        final_output_path.parent.mkdir(parents=True, exist_ok=True)

        captured_at = datetime.now().isoformat(timespec="microseconds")

        try:
            logger.info("Capturing image: %s", final_output_path)

            self._camera.capture_file(str(final_output_path))

            self._validate_captured_file(final_output_path)

            file_size = final_output_path.stat().st_size

            logger.info(
                "Image captured successfully: %s (%s bytes)",
                final_output_path,
                file_size,
            )

            return CaptureResult(
                image_path=final_output_path,
                captured_at=captured_at,
                width=self.width,
                height=self.height,
                file_size_bytes=file_size,
            )

        except Exception as exc:
            raise CameraCaptureError(
                f"Failed to capture image at {final_output_path}"
            ) from exc

    def _build_output_path(self, prefix: str | None = None) -> Path:
        """
        Build a timestamped image path.
        """

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_prefix = prefix or self.filename_prefix
        filename = f"{safe_prefix}_{timestamp}.jpg"
        return self.output_dir / filename

    @staticmethod
    def _validate_captured_file(image_path: Path) -> None:
        """
        Ensure the captured file exists and is not empty.
        """

        if not image_path.exists():
            raise CameraCaptureError(f"Image file was not created: {image_path}")

        if image_path.stat().st_size <= 0:
            raise CameraCaptureError(f"Image file is empty: {image_path}")


def capture_image(
    output_path: Path | None = None,
    prefix: str | None = None,
) -> CaptureResult:
    """
    Convenience function for one-off captures.

    Example:
        result = capture_image(prefix="manual_test")
    """

    with CameraCaptureService() as camera:
        return camera.capture_image(output_path=output_path, prefix=prefix)


__all__ = [
    "CameraCaptureError",
    "CaptureResult",
    "CameraCaptureService",
    "capture_image",
]
