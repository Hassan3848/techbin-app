# TechBin Web/Cloud Contract For Raspberry Pi

This document is based on the actual web repository plus the Raspberry Pi handoff. It contains no Pi token, password, service-role key, or other credential.

## Endpoint

```http
POST https://oqafmtuhfpapolylxvht.supabase.co/functions/v1/ingest-bin-state
x-device-token: <PI_DEVICE_TOKEN>
Content-Type: application/json
```

`x-device-token` authentication is unchanged. The Edge Function hashes the token and matches it against an active `pi_devices` row for the resolved bin.

## Final Categories

Use exactly these category names:

```text
cardboard
paper
plastic_glass
metal
trash
```

Do not send `organic`, separate `plastic`, or separate `glass` for the current Pi model.

## Final Side Values

Use exactly these side values:

```text
recyclable
non_recyclable
```

Current physical meaning from the Pi handoff:

```text
right side -> recyclable
left side -> non_recyclable
```

## Required Fields

Request-level requirements:

- Method must be `POST`.
- Header `x-device-token` is required.
- The token must belong to the same resolved `binId`.

Top-level payload:

- `orgId` is optional and defaults to `techbin`.
- `binCode` is optional and defaults to `BIN-001`.
- `status` is optional and defaults to normal server timestamp state.
- `sensors` is optional and defaults to `{}`.
- `statistics` is optional and defaults to `{}`.
- `faults` is optional and defaults to `{}`.
- `latestEvent` is optional. If omitted, the payload is a heartbeat/state update and no `bin_events` row is inserted.

Confirmed disposal event requirements:

- If `latestEvent` is present, it must be an object.
- `latestEvent.eventId` is required.
- If `latestEvent.category` is present, it must be one of the final category names above.
- If `latestEvent.expectedSide` or `latestEvent.disposedSide` is present, it must be one of the final side values above.

## Optional And Nullable Fields

Unavailable physical values may be omitted or set to `null`.

Allowed omitted/null values include:

- `sensors.temperature`
- `sensors.gasLevel`
- `faults.ir`
- `faults.servo`
- `faults.motor`
- `latestEvent.imageUrl`

The dashboard no longer displays missing `temperature` or `gasLevel` as invented zero readings. Missing values display as `-`.

## Sensor Contract

Preferred Pi sensor fields:

```json
{
  "sensors": {
    "leftFillLevel": 38,
    "rightFillLevel": 61,
    "fillLevel": 61,
    "temperature": null,
    "gasLevel": null
  }
}
```

`leftFillLevel` and `rightFillLevel` are the real compartment fill values.

`fillLevel` is optional backward compatibility only. If the Pi sends it, use an overall value such as max or average. The current examples use max.

## Statistics Contract

The Pi should send full current totals, not `+1` increments:

```json
{
  "statistics": {
    "totalItems": 24,
    "cardboard": 5,
    "paper": 4,
    "plastic_glass": 9,
    "metal": 2,
    "trash": 4,
    "recyclableItems": 20,
    "nonRecyclableItems": 4,
    "correctDisposals": 22,
    "incorrectDisposals": 2
  }
}
```

## latestEvent Contract

Supported fields:

```text
eventId
timestamp
label
category
recyclable
expectedSide
disposedSide
correct
confidence
placementConfirmed
modelVersion
classificationSource
imageUrl
```

Dedicated `bin_events` columns store:

```text
event_id
timestamp
label
category
recyclable
expected_side
disposed_side
correct
confidence
image_url
```

The full event object is also stored in `bin_events.payload` and `bin_states.latest_event`, so `placementConfirmed`, `modelVersion`, and `classificationSource` are preserved even though they do not have dedicated columns.

## Idempotent Retry Behavior

`bin_events.event_id` was added.

A unique index on `(bin_id, event_id)` prevents retrying the same Pi disposal event from creating duplicate history rows.

Important behavior:

- The latest bin state is updated before event insertion.
- A repeated `eventId` is safe: `bin_states` still updates, while `bin_events` does not duplicate the existing event.
- A heartbeat with no `latestEvent` updates `bin_states` and `pi_devices.last_seen`, but does not insert a `bin_events` row.

## Confirmed Cardboard Disposal Payload

```json
{
  "orgId": "techbin",
  "binCode": "BIN-001",
  "status": {
    "state": "normal",
    "message": "Running"
  },
  "sensors": {
    "leftFillLevel": 38,
    "rightFillLevel": 61,
    "fillLevel": 61,
    "temperature": null,
    "gasLevel": null
  },
  "statistics": {
    "totalItems": 24,
    "cardboard": 5,
    "paper": 4,
    "plastic_glass": 9,
    "metal": 2,
    "trash": 4,
    "recyclableItems": 20,
    "nonRecyclableItems": 4,
    "correctDisposals": 22,
    "incorrectDisposals": 2
  },
  "faults": {
    "camera": false,
    "ultrasonic": false,
    "network": false
  },
  "latestEvent": {
    "eventId": "pi-BIN-001-20260626T120000Z-000001",
    "timestamp": "2026-06-26T12:00:00Z",
    "label": "cardboard box",
    "category": "cardboard",
    "recyclable": true,
    "expectedSide": "recyclable",
    "disposedSide": "recyclable",
    "correct": true,
    "confidence": 0.91,
    "placementConfirmed": true,
    "modelVersion": "techbin-effnetv2-v1",
    "classificationSource": "camera",
    "imageUrl": null
  }
}
```

## Heartbeat Payload With No latestEvent

This updates state only. It must not create a `bin_events` row.

```json
{
  "orgId": "techbin",
  "binCode": "BIN-001",
  "status": {
    "state": "normal",
    "message": "Heartbeat"
  },
  "sensors": {
    "leftFillLevel": 38,
    "rightFillLevel": 61,
    "fillLevel": 61,
    "temperature": null,
    "gasLevel": null
  },
  "statistics": {
    "totalItems": 24,
    "cardboard": 5,
    "paper": 4,
    "plastic_glass": 9,
    "metal": 2,
    "trash": 4,
    "recyclableItems": 20,
    "nonRecyclableItems": 4,
    "correctDisposals": 22,
    "incorrectDisposals": 2
  },
  "faults": {
    "camera": false,
    "ultrasonic": false,
    "network": false
  }
}
```

## Migration Files Changed

- `supabase/migrations/20260626163000_add_bin_event_idempotency.sql`
  - Adds `bin_events.event_id`.
  - Adds unique index `bin_events_bin_event_id_unique` on `(bin_id, event_id)`.
- `supabase/schema.sql`
  - Updated canonical schema with `event_id` and the unique index.

## Edge Function Files Changed

- `supabase/functions/ingest-bin-state/index.ts`
  - Keeps `x-device-token` authentication unchanged.
  - Requires `latestEvent.eventId` when `latestEvent` is present.
  - Validates event categories.
  - Validates side values.
  - Stores `event_id`.
  - Uses idempotent upsert with `onConflict: "bin_id,event_id"` and `ignoreDuplicates: true`.
  - Still updates `bin_states` for repeated event IDs and heartbeats.

## Dashboard Files Changed

- `src/shared/realtimePipeline.ts`
  - Added `leftFillLevel`, `rightFillLevel`.
  - Replaced old category counters with `cardboard`, `paper`, `plastic_glass`, `metal`, `trash`.
  - Added event fields including `eventId`, `placementConfirmed`, `modelVersion`, and `classificationSource`.
  - Reads `bin_events.event_id`.
- `src/features/analytics/AnalyticsPage.tsx`
  - Uses final TechBin categories.
  - Treats `trash` as non-recyclable and the other current categories as recyclable.
- `src/features/monitoring/RealTimeMonitoringPage.tsx`
  - Displays left and right fill levels.
  - Shows missing temperature/gas as `-`, not `0`.
- `src/features/bin-health/BinHealthStatusPage.tsx`
  - Shows left/right fill details.
  - Does not display omitted IR or metal hardware as fake OK sensors.
- `package.json`
  - Added `test:pi-ingest-duplicate`.
- `scripts/test-pi-ingest.sh`
  - Updated payload to final TechBin categories, fill fields, nullable unavailable sensor values, and required `eventId`.
- `scripts/test-pi-ingest-duplicate.sh`
  - Added duplicate event ID retry test script.

## Test Results

Local build:

```text
pnpm build
result: passed
```

Manual ingest script:

```text
pnpm test:pi-ingest
result: not executed against Supabase because TECHBIN_DEVICE_TOKEN is not set in this shell.
```

Duplicate eventId retry script:

```text
pnpm test:pi-ingest-duplicate
result: not executed against Supabase because TECHBIN_DEVICE_TOKEN is not set in this shell.
```

Supabase CLI:

```text
supabase status/help checks failed inside the sandbox because the CLI tried to write telemetry under /Users/apple/.supabase.
```

To run the live ingest tests after setting a real token locally:

```bash
TECHBIN_DEVICE_TOKEN=tb_pi_... pnpm test:pi-ingest
TECHBIN_DEVICE_TOKEN=tb_pi_... pnpm test:pi-ingest-duplicate
```

Do not commit or paste the token.
