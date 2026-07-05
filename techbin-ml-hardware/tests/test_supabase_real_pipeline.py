"""
Dry-run tests for the permanent real-device Supabase pipeline.

Run from project root:
    PYTHONPATH=. python3 tests/test_supabase_real_pipeline.py
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.engine.real_device_pipeline import (
    RealDeviceDisposalPipeline,
    RealDevicePipelineConfig,
)
from app.ml.effnetv2 import RealPredictionResult
from app.telemetry.supabase import build_heartbeat_payload, build_latest_event
from app.telemetry.totals import LocalTotalsStore
from app.telemetry.uploader import TelemetryUploader, TransportResponse


class StaticTransport:
    def __init__(self, responses: list[TransportResponse]) -> None:
        self.responses = list(responses)
        self.sent_payloads: list[dict] = []

    def send(self, payload: dict) -> TransportResponse:
        self.sent_payloads.append(payload)
        if self.responses:
            return self.responses.pop(0)
        return TransportResponse(ok=True, status_code=200, message="ok")


class DictResult:
    def __init__(self, data: dict) -> None:
        self.data = data

    def to_dict(self) -> dict:
        return self.data


class FakeSessionDetector:
    def update(self) -> DictResult:
        return DictResult({"sessionStarted": True, "sessionActive": True})


class FakeSideDetector:
    def __init__(self, *, side: str | None = "right", valid: bool = True) -> None:
        self.side = side
        self.valid = valid
        self.baseline_captured = False

    def capture_baseline(self) -> None:
        self.baseline_captured = True

    def detect_once(self) -> DictResult:
        detected = self.side if self.valid else "unknown"
        return DictResult(
            {
                "valid": self.valid,
                "detectedSide": detected,
                "disposalSide": self.side if self.valid else None,
                "faultCode": None if self.valid else "no_compartment_disturbance",
            }
        )


class FakeCapacityMonitor:
    def check_all(self) -> dict:
        return {
            "overallValid": True,
            "left": {
                "fillLevel": {
                    "fillPercentage": 38,
                }
            },
            "right": {
                "fillLevel": {
                    "fillPercentage": 61,
                }
            },
        }


class FakeStack:
    def __init__(self, *, side: str | None = "right", side_valid: bool = True) -> None:
        self.session_detector = FakeSessionDetector()
        self.side_detector = FakeSideDetector(side=side, valid=side_valid)
        self.capacity_monitor = FakeCapacityMonitor()


class FakeClassifier:
    def __init__(self, prediction: RealPredictionResult) -> None:
        self.prediction = prediction

    def capture_average_prediction(self, camera) -> RealPredictionResult:
        return self.prediction


def prediction(
    *,
    category: str = "cardboard",
    confidence: float = 0.91,
    margin: float = 0.20,
    accepted: bool = True,
) -> RealPredictionResult:
    recyclable = category != "trash"
    return RealPredictionResult(
        category=category,
        label=category,
        confidence=confidence,
        margin=margin,
        accepted=accepted,
        rejectionReason=None if accepted else "low_margin:0.050<min:0.120",
        expectedSide="recyclable" if recyclable else "non_recyclable",
        recyclable=recyclable,
        modelVersion="test-model",
        classificationSource="camera",
        inferenceBackend="dry_run",
        inferenceTimeMs=1.0,
        imagePath="/tmp/test.jpg",
        top3=[
            {"label": category, "confidence": confidence},
            {"label": "trash", "confidence": confidence - margin},
        ],
        rawOutput={},
    )


def build_pipeline(
    *,
    tmp: Path,
    side: str | None,
    side_valid: bool,
    pred: RealPredictionResult,
    transport: StaticTransport | None = None,
) -> RealDeviceDisposalPipeline:
    uploader = TelemetryUploader(
        transport=transport
        or StaticTransport([TransportResponse(ok=False, status_code=None, message="dry")]),
        queue_root=tmp / "queue",
        max_retries=3,
    )

    return RealDeviceDisposalPipeline(
        hardware_stack=FakeStack(side=side, side_valid=side_valid),
        classifier=FakeClassifier(pred),
        totals_store=LocalTotalsStore(tmp / "totals.json"),
        telemetry_uploader=uploader,
        config=RealDevicePipelineConfig(
            item_position_seconds=0.0,
            side_confirm_timeout_seconds=0.01,
            side_poll_seconds=0.0,
            telemetry_mode="queue",
        ),
    )


def test_confirmed_recyclable_event(tmp: Path) -> None:
    result = build_pipeline(
        tmp=tmp,
        side="right",
        side_valid=True,
        pred=prediction(category="cardboard"),
    ).process_once(camera=object())

    assert result.status == "processed"
    assert result.supabasePayload is not None
    assert result.supabasePayload["latestEvent"]["category"] == "cardboard"
    assert result.supabasePayload["latestEvent"]["correct"] is True
    assert result.totals is not None
    assert result.totals["totalItems"] == 1
    assert result.totals["cardboard"] == 1
    assert result.totals["correctDisposals"] == 1
    assert result.totals["incorrectDisposals"] == 0


def test_confirmed_incorrect_disposal(tmp: Path) -> None:
    result = build_pipeline(
        tmp=tmp,
        side="left",
        side_valid=True,
        pred=prediction(category="cardboard"),
    ).process_once(camera=object())

    assert result.status == "processed"
    assert result.supabasePayload is not None
    event = result.supabasePayload["latestEvent"]
    assert event["expectedSide"] == "recyclable"
    assert event["disposedSide"] == "non_recyclable"
    assert event["correct"] is False
    assert result.totals is not None
    assert result.totals["incorrectDisposals"] == 1


def test_uncertain_prediction_does_not_update_totals(tmp: Path) -> None:
    result = build_pipeline(
        tmp=tmp,
        side="right",
        side_valid=True,
        pred=prediction(category="cardboard", accepted=False, margin=0.05),
    ).process_once(camera=object())

    assert result.status == "uncertain_prediction"
    assert result.supabasePayload is None
    assert result.totals is None
    assert not (tmp / "totals.json").exists()


def test_unconfirmed_side_does_not_update_totals(tmp: Path) -> None:
    result = build_pipeline(
        tmp=tmp,
        side=None,
        side_valid=False,
        pred=prediction(category="paper"),
    ).process_once(camera=object())

    assert result.status == "side_unconfirmed"
    assert result.supabasePayload is None
    assert result.totals is None
    assert not (tmp / "totals.json").exists()


def test_duplicate_queue_retry_preserves_event_id(tmp: Path) -> None:
    event_id = "pi-BIN-001-test-duplicate"
    payload = {
        "orgId": "techbin",
        "binCode": "BIN-001",
        "status": {"state": "normal", "message": "Running"},
        "sensors": {"leftFillLevel": 1, "rightFillLevel": 2, "fillLevel": 2},
        "statistics": {},
        "faults": {},
        "latestEvent": build_latest_event(
            event_id=event_id,
            category="paper",
            disposed_side="recyclable",
            confidence=0.9,
            model_version="test-model",
        ),
    }

    transport = StaticTransport(
        [
            TransportResponse(ok=False, status_code=None, message="offline"),
            TransportResponse(ok=True, status_code=200, message="sent"),
        ]
    )
    uploader = TelemetryUploader(
        transport=transport,
        queue_root=tmp / "queue",
        max_retries=3,
    )

    first = uploader.upload_or_queue(
        payload,
        prefix="supabase_event",
        payload_id=event_id,
    )
    assert first.status == "queued"
    assert first.payload_id == event_id

    pending_files = list((tmp / "queue" / "pending").glob("*.json"))
    assert len(pending_files) == 1

    queued = json.loads(pending_files[0].read_text(encoding="utf-8"))
    assert queued["payloadId"] == event_id
    assert queued["payload"]["latestEvent"]["eventId"] == event_id

    retry_results = uploader.upload_pending()
    assert retry_results[0].status == "sent"
    assert retry_results[0].payload_id == event_id

    sent_files = list((tmp / "queue" / "sent").glob("*.json"))
    assert len(sent_files) == 1
    sent = json.loads(sent_files[0].read_text(encoding="utf-8"))
    assert sent["payloadId"] == event_id
    assert sent["payload"]["latestEvent"]["eventId"] == event_id


def test_heartbeat_has_no_latest_event() -> None:
    payload = build_heartbeat_payload(
        statistics={"totalItems": 3, "paper": 1},
        sensors={"leftFillLevel": 38, "rightFillLevel": 61, "fillLevel": 61},
        status_message="Heartbeat",
    )

    assert "latestEvent" not in payload
    assert payload["status"]["message"] == "Heartbeat"
    assert payload["sensors"]["leftFillLevel"] == 38


def main() -> None:
    with TemporaryDirectory(prefix="techbin_supabase_tests_") as tmpdir:
        tmp = Path(tmpdir)
        test_confirmed_recyclable_event(tmp / "confirmed_recyclable")
        test_confirmed_incorrect_disposal(tmp / "incorrect")
        test_uncertain_prediction_does_not_update_totals(tmp / "uncertain")
        test_unconfirmed_side_does_not_update_totals(tmp / "unconfirmed")
        test_duplicate_queue_retry_preserves_event_id(tmp / "duplicate")
        test_heartbeat_has_no_latest_event()

    print("All Supabase real pipeline dry-run tests passed.")


if __name__ == "__main__":
    main()
