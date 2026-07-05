# Pi Supabase Implementation Report

## Changed Files

Permanent source/runtime:

- `app/config.py`
- `app/ml/effnetv2.py`
- `app/telemetry/totals.py`
- `app/telemetry/supabase.py`
- `app/telemetry/uploader.py`
- `app/engine/real_device_pipeline.py`
- `app/main_real_device.py`

Dry-run tests:

- `tests/test_supabase_real_pipeline.py`

Report:

- `PI_SUPABASE_IMPLEMENTATION_REPORT.md`

Dry-run test artifacts created locally:

- `logs/supabase_event_20260626_221935_833912.json`
- `logs/supabase_event_20260626_221935_838215.json`
- `logs/supabase_event_20260626_222028_237556.json`
- `logs/supabase_event_20260626_222028_245217.json`

No real device token was added to source, tests, logs, or this report.

## Permanent Runtime Command

```bash
PYTHONPATH=. python3 -m app.main_real_device --telemetry-mode upload_or_queue --json
```

The command runs one real disposal session:

front-session trigger -> side baseline -> item positioning wait -> real Pi Camera + EfficientNetV2 inference -> confidence/margin validation -> ultrasonic side confirmation -> capacity/light refresh -> confirmed event log -> persistent totals update -> Supabase upload-or-queue.

Existing mock runtimes remain intact:

- `python3 -m app.main_runtime`
- `python3 -m app.main_manual`

## Required Environment Variables

Required for real Supabase upload:

```bash
export TECHBIN_SUPABASE_URL="https://oqafmtuhfpapolylxvht.supabase.co"
export TECHBIN_ORG_ID="techbin"
export TECHBIN_BIN_CODE="BIN-001"
export TECHBIN_DEVICE_TOKEN="<set locally only>"
export TECHBIN_SUPABASE_TIMEOUT_SECONDS="10"
```

Required for real model inference:

```bash
export TECHBIN_MODEL_PACKAGE_PATH="/home/hassan/TechBin/model_tests/techbin_effnetv2_pi_test_package"
export TECHBIN_MODEL_VERSION="techbin-effnetv2-v1"
```

Optional tuning values, defaulting to the proven script behavior:

```bash
export TECHBIN_REAL_MIN_CONFIDENCE="0.60"
export TECHBIN_REAL_MIN_MARGIN="0.12"
```

Future metal override switch, disabled by default:

```bash
export TECHBIN_ENABLE_METAL_OVERRIDE="0"
```

Only set `TECHBIN_ENABLE_METAL_OVERRIDE=1` after the metal sensor hardware path is validated.

## Exact Model Package Setup

`TECHBIN_MODEL_PACKAGE_PATH` must point to a directory containing:

- `techbin_effnetv2_camera_dynamic_range.tflite`
- `labels.json`
- `preprocessing_config.json`

The permanent reusable model code is in `app/ml/effnetv2.py`. It preserves the proven Pi behavior from `scripts/test_real_camera_ai_hardware_flow.py`:

- Picamera2 RGB888 preview frames.
- Red/blue channel correction: `frame[:, :, [2, 1, 0]]`.
- `preprocessing_config.json` image size.
- EfficientNetV2 input values in `0..255`.
- Five-frame average.
- Confidence threshold `0.60`.
- Top-2 margin threshold `0.12`.
- Current categories exactly: `cardboard`, `paper`, `plastic_glass`, `metal`, `trash`.

## Supabase Payload

Implemented in `app/telemetry/supabase.py`.

The module sends the deployed contract shape:

- `orgId`
- `binCode`
- `status`
- `sensors.leftFillLevel`
- `sensors.rightFillLevel`
- `sensors.fillLevel`
- `sensors.temperature: null`
- `sensors.gasLevel: null`
- `statistics`
- `faults`
- optional `latestEvent`

For confirmed disposal events, `latestEvent.eventId` is generated before queueing and preserved through local logs, queue files, and retry uploads.

Heartbeat payloads are supported with no `latestEvent`, so they update `bin_states` without inserting a `bin_events` row.

## Queue/Retry Behavior

The implementation reuses `app/telemetry/uploader.py`.

Changes made:

- `TelemetryUploader.upload_or_queue()` now accepts optional `payload_id`.
- The real pipeline passes `eventId` as that `payload_id`.
- Pending queue envelopes therefore preserve the same ID as `latestEvent.eventId`.
- `upload_pending()` retries the same queued payload and keeps the same event ID.

No separate queue was added.

Default queue location remains:

```text
logs/telemetry_queue/
```

## Persistent Totals

Implemented in `app/telemetry/totals.py`.

Default totals file:

```text
logs/supabase_totals.json
```

Totals are updated only after:

- AI prediction is accepted, and
- physical side placement is confirmed.

Wrong but confirmed placements create an event and increment `incorrectDisposals`.

Uncertain predictions and unconfirmed placements do not create cloud disposal events and do not update totals.

Tracked totals:

- `totalItems`
- `cardboard`
- `paper`
- `plastic_glass`
- `metal`
- `trash`
- `recyclableItems`
- `nonRecyclableItems`
- `correctDisposals`
- `incorrectDisposals`

## Hardware Still Physically Pending

Not implemented as physical Supabase values:

- Temperature sensor.
- Gas sensor.
- IR sensor.
- Motor routing.
- Servo/flap control.
- Image upload URL.
- Voice feedback to Supabase.

Metal sensor:

- Code support exists.
- GPIO remains disabled in `app/sensors/pin_map.py`.
- Supabase metal override helper exists but is blocked unless `TECHBIN_ENABLE_METAL_OVERRIDE=1`.
- Voice feedback remains local only and is not connected to Supabase.

## Test Results

Focused dry-run pipeline test:

```text
PYTHONPATH=. python3 tests/test_supabase_real_pipeline.py
result: passed
```

Covered cases:

- confirmed recyclable event
- confirmed incorrect disposal
- uncertain prediction
- unconfirmed side placement
- duplicate queue retry preserving the same `eventId`
- heartbeat with no `latestEvent`

Syntax compile:

```text
PYTHONPATH=. python3 -m py_compile app/config.py app/ml/effnetv2.py app/telemetry/totals.py app/telemetry/supabase.py app/telemetry/uploader.py app/engine/real_device_pipeline.py app/main_real_device.py tests/test_supabase_real_pipeline.py
result: passed
```

## Exact Next Command For Real Pi-To-Supabase Test

Set the real token only in the Pi shell or service environment, never in source:

```bash
export TECHBIN_SUPABASE_URL="https://oqafmtuhfpapolylxvht.supabase.co"
export TECHBIN_ORG_ID="techbin"
export TECHBIN_BIN_CODE="BIN-001"
export TECHBIN_DEVICE_TOKEN="<real Pi token>"
export TECHBIN_SUPABASE_TIMEOUT_SECONDS="10"
export TECHBIN_MODEL_PACKAGE_PATH="/home/hassan/TechBin/model_tests/techbin_effnetv2_pi_test_package"
export TECHBIN_MODEL_VERSION="techbin-effnetv2-v1"
PYTHONPATH=. python3 -m app.main_real_device --telemetry-mode upload_or_queue --json
```
