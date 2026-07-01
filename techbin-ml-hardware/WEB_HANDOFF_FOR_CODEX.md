# Web Handoff For Codex

Source of truth: this report was written from the Raspberry Pi repository at `/home/hassan/techbin-device`. It does not assume hardware or features exist just because the web handoff mentions them.

## 1. Repository Structure And Runtime Entrypoint

The Pi repo is mostly Python with one Arduino sketch.

- `app/main_runtime.py`: current CLI runtime entrypoint, but it is explicitly a safe mock runtime. It waits for manual/CLI triggers, captures an image, uses `MockWasteClassifier`, accepts a manual disposal side, runs `EventProcessor`, saves JSON logs, and queues telemetry.
- `app/main_manual.py`: manual one-event runner for demos/tests before full real runtime integration.
- `app/engine/`: event processing, confidence checks, disposal validation, and hardware-flow orchestration.
- `app/sensors/`: ultrasonic, direct-Pi hardware stack, Arduino serial stack, capacity monitoring, traffic lights, metal sensor support, health checks, and pin map.
- `app/camera/`: Raspberry Pi camera capture service.
- `app/ml/`: labels, preprocessing utilities, mock classifier, and unimplemented TFLite classifier placeholder.
- `app/telemetry/`: current local payload builders, queue/uploader, HTTP transport, and fault reporter.
- `scripts/`: hardware/integration scripts. Several scripts touch real GPIO/camera and are not permanent runtime code.
- `tests/`: unit/integration/real-hardware tests.
- `arduino/techbin_arduino_sensor_controller/`: Arduino Uno sketch for left/right ultrasonic readings over USB serial.
- `models/`: exists but contains no model files in this repo.
- `captures/` and `logs/`: runtime artifacts.

Main permanent runtime processing boundary: `app/engine/event_processor.py::EventProcessor.process_disposal_event()`.

Main hardware orchestration boundary: `app/engine/hardware_event_flow.py::HardwareEventFlow.process_once()`, but the fully real camera+AI behavior is currently in a standalone script, not wired into the permanent runtime.

## 2. Sensor Files And Hardware Status

Front sensor:

- `app/sensors/session_detector.py` owns front ultrasonic session detection.
- It returns `SessionDetectionResult` with `sessionActive`, `sessionStarted`, `sessionEnded`, `presenceDetected`, `distanceCm`, `valid`, and `faultCode`.
- `app/sensors/direct_pi_stack.py` configures the front HC-SR04 with presence threshold `35.0cm`, `stable_presence_reads=2`, and `stable_absence_reads=3`.

Left/right ultrasonic sensors:

- `app/sensors/ultrasonic.py` provides `UltrasonicDistanceSensor`, simulated backend, and gpiozero backend.
- `app/sensors/side_detector.py` compares left/right baseline and current distances to detect `left`, `right`, `unknown`, or `ambiguous`.
- Direct-Pi pin map: front TRIG/ECHO `23/24`, left `5/6`, right `16/20`, all enabled in `app/sensors/pin_map.py`.
- Arduino path also exists: `app/sensors/arduino_bridge.py`, `arduino_ultrasonic_adapter.py`, `arduino_side_detection_monitor.py`, `arduino_side_confirmation.py`, and `arduino_side_confirmation_runner.py`.

Traffic lights:

- `app/sensors/capacity_indicator.py` controls left/right capacity lights with simulated and gpiozero backends.
- Pin map enables left light red/yellow/green `17/27/22` and right `12/13/26`.
- Meaning is green = low fill/enough space, yellow = half/medium, red = full/high, off = unknown/fault.

Side confirmation:

- Direct-Pi side confirmation is `DualUltrasonicSideDetector.detect_once()`.
- Arduino side confirmation is more mature for repeated-window decisions: `FastArduinoSideConfirmationRunner.confirm_once()` can confirm in about `1.0-1.5s` when clear.
- The current permanent `HardwareEventFlow` uses direct-Pi `DualUltrasonicSideDetector`, not the Arduino confirmation runner.

Capacity monitoring:

- `app/sensors/capacity_monitor.py` reads left/right ultrasonic sensors, estimates fill, and updates lights.
- `app/sensors/fill_level.py` converts distance to fill percentage.
- `app/sensors/capacity_calibration.py` contains current calibrated empty distances: left `38.21cm`, right `39.00cm`; temporary full distances are `5.00cm` both sides; low threshold `40%`, full threshold `80%`.

Metal detector:

- `app/sensors/metal_sensor.py` has simulated and gpiozero support, debounced reads, and stuck-signal health checks.
- `app/sensors/pin_map.py` defines metal GPIO `21`, but `enabled=False`.
- Current runtime can pass `metal_detected` into confidence logic, but no permanent flow is reading real metal sensor hardware yet.

## 3. Camera And AI Inference

Permanent camera code:

- `app/camera/capture.py` owns `CameraCaptureService` and `capture_image()`.
- It uses `picamera2`, still capture resolution from config defaults `1280x720`, warmup `1.0s`, and writes timestamped JPGs under `captures/`.

Permanent ML code:

- `app/ml/infer.py` currently uses `MockWasteClassifier` by default.
- `TFLiteWasteClassifier` exists only as a placeholder and raises `NotImplementedError`.
- `app/ml/preprocess.py` supports RGB conversion, resize, batch dimension, `float32`/`uint8`, and normalization modes `none`, `zero_to_one`, `minus_one_to_one`, defaulting to `224x224`, `float32`, `zero_to_one`.
- `app/ml/labels.py` supports permanent labels: `cardboard`, `glass`, `metal`, `paper`, `plastic`, `trash`.

Current model package:

- No model files are present under repo `models/`.
- `scripts/test_real_camera_ai_hardware_flow.py` hardcodes an external model package: `/home/hassan/TechBin/model_tests/techbin_effnetv2_pi_test_package`.
- That script expects `techbin_effnetv2_camera_dynamic_range.tflite`, `labels.json`, and `preprocessing_config.json`.
- Its labels classify `cardboard`, `paper`, `plastic_glass` as recyclable and `trash` as non-recyclable.

Real integrated test preprocessing and rules:

- The standalone script uses Picamera2 preview `720x720` RGB888.
- It applies red/blue correction with `frame[:, :, [2, 1, 0]]`.
- It averages `5` frames at `0.20s` interval.
- It resizes according to `preprocessing_config.json`, usually `224x224`.
- It feeds EfficientNetV2 RGB `float32` values in range `0..255` because preprocessing is inside the model.
- It accepts predictions only when confidence is at least `0.60` and top-2 margin is at least `0.12`.

Permanent confidence rules:

- `app/config.py` default `TECHBIN_MIN_CONFIDENCE` is `0.70`.
- `app/engine/disposal_validator.py` rejects accepted analytics if confidence is below min.
- `app/engine/confidence_engine.py` can additionally require image capture, front session trigger, and compartment confirmation. Metal evidence creates warnings, not hard accept/reject.

Recyclable/non-recyclable decision logic:

- Permanent app labels map `cardboard`, `glass`, `metal`, `paper`, `plastic` to `recyclable`.
- Permanent app label `trash` maps to `non-recyclable`.
- Right side means recyclable. Left side means non-recyclable.
- The real camera script currently uses `plastic_glass`, which does not match permanent `app/ml/labels.py`; this must be reconciled before moving the real model into permanent runtime.

## 4. Current Disposal Flow

Permanent mock/manual flow:

1. `main_runtime.py` or `main_manual.py` builds a mock classifier.
2. `EventProcessor.process_disposal_event()` normalizes disposal side.
3. It captures or uses an image via `capture_image()`.
4. It runs `predict_image()`, currently mock unless a classifier is injected.
5. It builds a local disposal payload via `build_disposal_event_payload()`.
6. It adds `modelName` and `inferenceTimeMs`.
7. It evaluates confidence using ML confidence plus optional session/side/metal evidence.
8. It saves a JSON event under `logs/`.
9. It queues telemetry by default in `logs/telemetry_queue/pending/`.

Permanent hardware flow:

1. Optionally refresh capacity first if `HardwareEventFlowConfig.update_capacity_monitor=True`.
2. Capture left/right side baseline if enabled.
3. Read front session detector.
4. If `require_session_trigger=True` and no active session, return `no_session`.
5. Run side detector once.
6. If side is invalid or missing, return `side_detection_failed`.
7. Call `process_disposal_event()` with detected side, optional image path, optional classifier, session evidence, side confirmation evidence, and optional metal evidence.
8. Return a structured `HardwareEventFlowResult`.

Standalone real camera+AI+hardware script flow:

1. Build direct-Pi hardware stack.
2. Start Picamera2 preview.
3. Poll front session every `0.45s` until `sessionStarted`.
4. Capture side baseline.
5. Wait `2.5s` for item positioning.
6. Capture and average 5 camera predictions.
7. Reject if confidence `<0.60` or margin `<0.12`.
8. Decide suggested side from recyclable/non-recyclable label.
9. Poll side detector for up to `12s`.
10. Compare detected side to expected side.
11. Refresh capacity and traffic lights.
12. Stop camera and close stack. It writes no dashboard analytics.

Cleanup:

- `DirectPiHardwareStack.close()` turns indicators off and closes backends.
- Camera scripts call `camera.stop()` and `camera.close()`.

## 5. Test Scripts Versus Permanent Runtime Code

Permanent runtime/library code:

- `app/main_runtime.py`, `app/main_manual.py`
- `app/engine/*.py`
- `app/camera/capture.py`
- `app/ml/*.py`
- `app/sensors/*.py`
- `app/telemetry/*.py`
- `app/utils/event_logger.py`
- `app/config.py`, `app/logger.py`

Standalone/test-only scripts:

- Everything under `tests/` is test code.
- Everything under `scripts/` is script/test/demo code. Important real-hardware knowledge exists there, especially `scripts/test_real_camera_ai_hardware_flow.py`, but it is not permanent runtime.
- `archived_old_tests_*` and `backups/` are not active runtime.
- `captures/` and `logs/` are runtime artifacts.

Arduino:

- `arduino/techbin_arduino_sensor_controller/techbin_arduino_sensor_controller.ino` is firmware for Arduino side ultrasonic acquisition. The Pi permanent modules can consume it, but current direct-Pi runtime stack does not require Arduino.

## 6. Counters, Events, Faults, Config, HTTP, Queue, Event IDs

Counters/statistics:

- No permanent running totals exist for `totalItems`, per-category counts, recyclable/non-recyclable totals, correct disposals, or incorrect disposals.
- Existing files contain per-event fields only: `predictedClass`, `recyclability`, `isCorrectDisposal`, `isEventAccepted`, etc.
- Supabase integration must add persistent local totals if the web expects full current totals.

Event objects:

- Disposal payloads are built in `app/telemetry/payloads.py::build_disposal_event_payload()`.
- `EventProcessingResult` wraps the final payload, log path, image path, inference details, telemetry result, and source.
- `HardwareEventFlowResult` wraps session detection, side detection, capacity result, event processing, payload, telemetry, and fault code.

Faults:

- `app/telemetry/fault_reporter.py` builds and queues fault payloads.
- `app/sensors/health_check.py` checks runtime directories, disk space, camera command/detection, telemetry queue, model files, and placeholder ultrasonic/metal/audio status.
- Sensor modules return structured fault codes for invalid readings, missing baseline, no disturbance, ambiguity, GPIO/import failures, and disabled hardware.

Configuration:

- `app/config.py` reads environment variables with `os.getenv()`.
- Supported env vars include camera dimensions/warmup, log settings, `TECHBIN_MIN_CONFIDENCE`, mock class/confidence, `TECHBIN_BIN_ID`, and `TECHBIN_ORG_ID`.
- There is no `.env` loader in code and no `python-dotenv` usage found.
- There is no current `TECHBIN_SUPABASE_URL`, `TECHBIN_BIN_CODE`, or `TECHBIN_DEVICE_TOKEN` support.

HTTP libraries/cloud upload:

- `app/telemetry/uploader.py` uses Python standard library `urllib.request` and `urllib.error`.
- No `requests`, `httpx`, or `aiohttp` dependency is needed for current HTTP support.
- `HttpJsonTransport` can POST JSON to an endpoint with custom headers.
- It is generic and does not yet know Supabase, `x-device-token`, bin state shape, or web payload mapping.

Offline queue/retry:

- Existing queue root is `logs/telemetry_queue/`.
- Pending, sent, and failed directories exist.
- `TelemetryUploader.enqueue()` creates a UUID `payloadId`.
- `upload_or_queue()` tries immediate upload and queues on failure.
- `upload_pending()` retries pending JSON envelopes.
- `max_retries` defaults to `3`; after that files move to `failed/`.

Unique event IDs:

- Queue envelopes have `payloadId` UUIDs, but disposal payloads do not currently include stable `eventId`.
- JSON log filenames include timestamps, but those are not payload IDs.
- For Supabase duplicate protection, add a stable per-disposal `eventId` into the actual payload, not only the queue envelope.

## 7. Safest Supabase Integration Points

Safest files/functions to add a future uploader:

- Add Supabase-specific payload mapping and/or transport under `app/telemetry/`, preferably a new file such as `app/telemetry/supabase.py`.
- Reuse `app/telemetry/uploader.py::TelemetryUploader` for queue/retry instead of inventing a second queue.
- Reuse `HttpJsonTransport` or add a small Supabase transport wrapper that sets `x-device-token` and posts to `/functions/v1/ingest-bin-state`.
- Add config/env support in `app/config.py::load_settings()` for `TECHBIN_SUPABASE_URL`, `TECHBIN_BIN_CODE`, `TECHBIN_DEVICE_TOKEN`, and optional upload mode/timeout.

Safest caller:

- `app/engine/event_processor.py::EventProcessor.process_disposal_event()` is the narrowest point for per-disposal uploads after prediction, validation, confidence checks, and local log save.
- The upload call should occur after `payload = _apply_confidence_decision_to_payload(...)` and after or alongside `save_event_log()`, using the existing `_handle_telemetry()` path.
- `app/engine/hardware_event_flow.py::HardwareEventFlow.process_once()` is the safest place to pass capacity/session/side evidence into a richer Supabase state builder, because it already has `session_result`, `side_result`, `capacity_result`, and `event_result`.

Do not put Supabase calls directly in low-level sensor modules, camera capture, or ML inference. Those modules should stay hardware/model-focused.

## 8. Pi Values That Map To Cloud Fields

Direct mappings available now:

- `orgId`: current `settings.device.org_id`, but default is `demo-org`; handoff wants `techbin`.
- `binCode`: does not exist; add env/config. Current code has `binId` default `TECHBIN-001`, not `BIN-001`.
- `status.state`: infer from flow/health. No direct permanent state object exists.
- `status.message`: infer from flow result or health summary.
- `sensors.fillLevel`: can map from `DualCapacityMonitorResult`. Need choose one aggregate number from left/right percentages, likely max of valid compartment fill percentages for dashboard simplicity.
- `latestEvent.timestamp`: current event payload `timestamp`.
- `latestEvent.label`: current payload `predictedClass`.
- `latestEvent.category`: current payload `predictedClass` or mapped web category. Needs label reconciliation for `plastic_glass`.
- `latestEvent.recyclable`: `payload["recyclability"] == "recyclable"`.
- `latestEvent.disposedSide`: map left to `non_recyclable` or `non-recyclable`, right to `recyclable`, depending web contract; current Pi stores physical `left`/`right`.
- `latestEvent.expectedSide`: same mapping from current `expectedSide`.
- `latestEvent.correct`: current `isCorrectDisposal`.
- `latestEvent.confidence`: current `confidence`.
- `latestEvent.imageUrl`: no upload exists; should be `null` initially.
- `faults.camera`: available from camera exceptions or health check.
- `faults.ultrasonic`: available from session/side/capacity fault codes.
- `faults.metal`: available if metal sensor enabled; currently disabled/not configured.
- `faults.network`: can be inferred from telemetry upload failure/queued state.

Statistics that can be derived only after adding counters:

- `statistics.totalItems`: count accepted events.
- `statistics.plastic`, `paper`, `glass`, `metal`, `organic`: no persistent counters now. Also `organic` is not a current Pi class.
- `statistics.recyclableItems`, `nonRecyclableItems`: count accepted events by `recyclability`.
- `statistics.correctDisposals`, `incorrectDisposals`: count accepted events by `isCorrectDisposal`.

Values that do not currently exist physically or in permanent runtime:

- Temperature sensor: not present.
- Gas sensor/gas level: not present.
- IR sensor: not present.
- Servo/flap control: not present.
- Motor routing: not present.
- Physical bin/flap routing actuator: not present.
- Raw image cloud upload URL: not present.
- Organic class: not present in Pi labels.

## 9. Risks Or Missing Work Before Supabase Integration

- Real model integration is not in permanent `app/ml/infer.py`; the only real model path is a standalone script and external package.
- Label mismatch: permanent code expects `plastic`, `glass`; real script uses `plastic_glass`.
- No persistent running totals exist, but web payload expects full totals.
- No `.env` loading exists; environment variables work only if set by shell/systemd.
- No Supabase-specific config exists for URL, bin code, or device token.
- Current queue UUID is not the same as a stable event ID inside payload.
- `HardwareEventFlowConfig.telemetry_mode` includes `"dry_run"` and `"upload"`, but `EventProcessor` only supports `"none"`, `"queue"`, and `"upload_or_queue"`; using unsupported modes through `HardwareEventFlow` would fail.
- Capacity update in `HardwareEventFlow` happens before event processing when enabled. The standalone real script refreshes capacity after confirmed disposal. Supabase payload likely needs post-disposal capacity.
- Metal sensor is disabled and should not be reported as physically available.
- Health monitor still says ultrasonic/metal are placeholders unless `require_*` flags are set, despite direct-Pi ultrasonic modules being active elsewhere.
- Real hardware posting must not block camera/sensor timing; use short HTTP timeout plus queue-first or upload-or-queue behavior.
- Web contract uses `binCode`, while current Pi config uses `binId`.

## 10. Recommended Minimal Integration Plan

1. Add Supabase config in `app/config.py` with env-only secrets: `TECHBIN_SUPABASE_URL`, `TECHBIN_BIN_CODE`, `TECHBIN_DEVICE_TOKEN`, optional `TECHBIN_SUPABASE_TIMEOUT_SECONDS`, and optional upload mode.
2. Add `app/telemetry/supabase.py` with:
   - `build_supabase_bin_state_payload(event_payload, totals, capacity_result=None, faults=None)`.
   - `build_supabase_transport(settings)` or `SupabaseIngestTransport` using `HttpJsonTransport` with `x-device-token`.
3. Add a tiny persistent totals store under `app/telemetry/` or `app/state/`, backed by a JSON file in `logs/`, updated only for accepted events. Store full totals, not increments.
4. Add a stable `eventId` per disposal payload at event-build time or immediately after event build. Use UUID and persist it through queue retries.
5. Wire the uploader through `EventProcessor.process_disposal_event()` using the existing `TelemetryUploader` queue/retry path. Do not call network directly from sensors.
6. For hardware flow, refresh capacity after accepted side confirmation and event processing, then include capacity in the Supabase state payload.
7. First test with `DryRunTransport` and one fake Supabase-shaped payload.
8. Then test `HttpJsonTransport` against the already verified Edge Function using a real `TECHBIN_DEVICE_TOKEN`.
9. Keep `imageUrl: null` for first integration.
10. Send after every accepted classification/disposal event. Optionally add a periodic health/state heartbeat later, but event upload is the minimal useful path.

First implementation should send full totals plus a stable `eventId`. Full totals make retries safer, and `eventId` gives the cloud a path to duplicate protection later.
