# TechBin Pi Integration Handoff For Codex

You are Codex running in the Raspberry Pi codebase. I need you to inspect the full Pi-side repository and explain how it should connect to the TechBin web application.

## Web Application Summary

The web application is `techbin-app-main`, a React + TypeScript + Vite dashboard connected to Supabase.

The web side already has:

- Supabase Auth for login.
- Role-based access using a `profiles` table.
- One Super Admin: `admin@techbin.com`.
- Org Admin and Viewer roles.
- Bin Registry for creating/managing bins.
- Pi Devices preview page for generating device tokens.
- Supabase Edge Function `ingest-bin-state` for receiving Raspberry Pi telemetry.
- Supabase Realtime dashboard pages that read from `bin_states` and `bin_events`.

The web/cloud pipeline is:

```text
Raspberry Pi -> Supabase Edge Function -> Supabase tables -> Web dashboard
```

The web app does not talk directly to the Pi. The Pi only talks to Supabase.

Important design decision:

The Pi should send processed results, not raw sensor/camera noise. The Pi code should do the local work: capture readings, run classification, decide recyclable/non-recyclable, decide whether the disposal was correct, update its local counters, then send a clean state/event payload to the cloud.

For example, if the Pi detects a plastic bottle and the user throws it into the correct recyclable side, the Pi should send the interpreted result:

- category is `plastic`
- recyclable is `true`
- expected side is `recyclable`
- disposed side is `recyclable`
- correct is `true`
- updated totals include one more total item, one more plastic item, one more recyclable item, and one more correct disposal

Prefer sending full current totals, such as `correctDisposals: 16`, instead of only sending increment commands like `correctDisposals +1`. Full totals are safer because if the Pi retries a request after a Wi-Fi issue, the cloud is less likely to double-count the same event.

Later, if the Pi code already has stable unique event IDs, we can also add duplicate protection by sending an `eventId` with each event.

## Supabase Project

Project ref:

```text
oqafmtuhfpapolylxvht
```

Project URL:

```text
https://oqafmtuhfpapolylxvht.supabase.co
```

Pi ingest endpoint:

```text
https://oqafmtuhfpapolylxvht.supabase.co/functions/v1/ingest-bin-state
```

The function uses `x-device-token` for Pi authentication. It does not require a Supabase user JWT.

## Current Demo Bin Contract

For the first demo, assume one bin:

```text
orgId: techbin
binCode: BIN-001
binId: techbin_BIN-001
```

The generated Pi token belongs to this bin. The raw token should live only in the Pi config or environment. Supabase stores only its hash in `pi_devices`.

Do not hardcode secrets into source if avoidable. Prefer `.env`, local config, or system environment variables.

Recommended Pi config:

```env
TECHBIN_SUPABASE_URL=https://oqafmtuhfpapolylxvht.supabase.co
TECHBIN_ORG_ID=techbin
TECHBIN_BIN_CODE=BIN-001
TECHBIN_DEVICE_TOKEN=tb_pi_REPLACE_WITH_REAL_TOKEN
```

## Payload Expected By The Web App

The Pi should send a POST request:

```http
POST https://oqafmtuhfpapolylxvht.supabase.co/functions/v1/ingest-bin-state
x-device-token: TECHBIN_DEVICE_TOKEN
Content-Type: application/json
```

Example payload:

```json
{
  "orgId": "techbin",
  "binCode": "BIN-001",
  "status": {
    "state": "normal",
    "message": "Running"
  },
  "sensors": {
    "fillLevel": 42,
    "temperature": 31,
    "gasLevel": 12
  },
  "statistics": {
    "totalItems": 18,
    "plastic": 8,
    "paper": 3,
    "glass": 0,
    "metal": 1,
    "organic": 6,
    "recyclableItems": 12,
    "nonRecyclableItems": 6,
    "correctDisposals": 15,
    "incorrectDisposals": 3
  },
  "faults": {
    "camera": false,
    "ir": false,
    "ultrasonic": false,
    "metal": false,
    "network": false
  },
  "latestEvent": {
    "timestamp": "2026-06-26T12:00:00Z",
    "label": "plastic bottle",
    "category": "plastic",
    "recyclable": true,
    "disposedSide": "recyclable",
    "expectedSide": "recyclable",
    "correct": true,
    "confidence": 0.93,
    "imageUrl": null
  }
}
```

This payload is intentionally a processed state payload. It is not meant to upload raw images, raw ultrasonic pulses, raw gas sensor voltage, or every intermediate ML value. Only send the values needed by the dashboard and debugging screens.

## What The Edge Function Does

The `ingest-bin-state` function:

- Reads `x-device-token`.
- Hashes the token.
- Checks `pi_devices` for a matching active token assigned to `techbin_BIN-001`.
- Updates `bin_states`.
- Inserts into `bin_events` when `latestEvent` is provided.
- Updates `pi_devices.last_seen`.

If the token is wrong, inactive, or belongs to a different bin, the request is rejected.

## What The Dashboard Uses

Dashboard pages read:

- `bins` for bin registry and basic bin metadata.
- `bin_states` for latest sensor/status/statistics/fault state.
- `bin_events` for disposal history.
- `pi_devices.last_seen` for device activity.

Important field mapping:

```text
sensors.fillLevel -> fill level display
sensors.temperature -> temperature display
sensors.gasLevel -> gas reading
statistics.totalItems -> dashboard totals
statistics.recyclableItems -> recyclable count
statistics.nonRecyclableItems -> non-recyclable count
statistics.correctDisposals -> correct disposal count
statistics.incorrectDisposals -> incorrect disposal count
faults.camera / faults.ir / faults.ultrasonic / faults.metal / faults.network -> fault pages
latestEvent.label -> last classified item
latestEvent.category -> item class/category
latestEvent.recyclable -> recyclable/non-recyclable UI
latestEvent.correct -> disposal correctness UI
```

## What I Need You To Inspect On Pi Side

Please inspect the Raspberry Pi codebase and report:

1. Main entrypoint file.
2. Files that read sensors.
3. Files that handle camera capture.
4. Files that run ML/classification.
5. Files that decide recyclable vs non-recyclable.
6. Files that control bin/flap/servo/motor routing.
7. Current data object or variables that represent:
   - fill level
   - temperature
   - gas level
   - detected label
   - confidence
   - recyclable result
   - disposal side
   - faults
8. Whether the Pi code is Python, Node, mixed, or something else.
9. Whether there is already an HTTP client or cloud upload module.
10. Current timing from image capture to classification result.
11. Whether requests should be sent:
   - after every classification event
   - on a fixed interval
   - both
12. Where a `.env` or config file should be added.
13. Whether offline queue/retry is already implemented.
14. What dependencies are already installed for HTTP requests.
15. Any hardware-specific constraints that affect cloud posting.
16. Whether the Pi already keeps local running totals, or whether totals need to be added.
17. Whether the Pi has a unique ID for each detected disposal event that could be used as `eventId` later.

## What I Want You To Propose

After inspecting the Pi repository, propose the smallest clean integration plan:

- Which file should own the Supabase upload function.
- Which existing code should call it.
- Exact payload mapping from Pi variables to the web payload.
- Where config/secrets should live.
- Retry behavior if Wi-Fi/cloud is unavailable.
- How to avoid blocking the ML/sensor loop.
- How to test with one fake payload before using real hardware readings.
- Whether the first implementation should send full totals only, or full totals plus a unique event ID.

Do not rewrite the full Pi app immediately. First report the repo structure, current flow, and safest integration points.

## Return Handoff File To Create

Please also create a markdown file in the Raspberry Pi repository named:

```text
WEB_HANDOFF_FOR_CODEX.md
```

This file is for Codex working on the web application side. Write it with enough explanation that the web-side Codex can understand the full Pi story without guessing.

Include:

- Pi repository structure.
- Main runtime entrypoint.
- Sensor pipeline explanation.
- Camera and ML/classification pipeline explanation.
- Recyclable/non-recyclable decision logic.
- Disposal correctness logic.
- Servo/flap/bin routing logic.
- Current counters/statistics available in code.
- Current fault/error detection available in code.
- Exact variables that should map to the Supabase payload.
- Which file should send the cloud request.
- Which existing flow should call the cloud request.
- Any missing Pi-side pieces before integration can be completed.
- Any assumptions or risks the web-side Codex should know.

Use clear section headings and explain the flow in normal language, not only file names. The goal is that both sides understand each other before permanent Pi-side integration changes are made.

## Known Verified Web-Side Test

A manual test payload was already sent from the web repo and returned:

```json
{"ok":true,"binId":"techbin_BIN-001"}
```

That means the cloud endpoint accepts a valid Pi token and writes to Supabase correctly.

The next missing work is Pi-side implementation: read real values, build the payload, send it to `ingest-bin-state`, and handle retries safely.
