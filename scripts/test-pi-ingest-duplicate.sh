#!/usr/bin/env bash
set -Eeuo pipefail

SUPABASE_URL="${VITE_SUPABASE_URL:-https://oqafmtuhfpapolylxvht.supabase.co}"
ORG_ID="${TECHBIN_ORG_ID:-techbin}"
BIN_CODE="${TECHBIN_BIN_CODE:-BIN-001}"
EVENT_ID="${TECHBIN_EVENT_ID:-duplicate-test-$(date -u +"%Y%m%dT%H%M%SZ")}"

if [[ -z "${TECHBIN_DEVICE_TOKEN:-}" ]]; then
  printf 'TECHBIN_DEVICE_TOKEN is required.\n' >&2
  printf 'Generate a Pi token in the dashboard, then run:\n' >&2
  printf '  TECHBIN_DEVICE_TOKEN=tb_pi_... pnpm test:pi-ingest-duplicate\n' >&2
  exit 1
fi

payload() {
  printf '{
    "orgId": "%s",
    "binCode": "%s",
    "status": {
      "state": "normal",
      "message": "Duplicate eventId retry test"
    },
    "sensors": {
      "leftFillLevel": 38,
      "rightFillLevel": 61,
      "fillLevel": 61,
      "temperature": null,
      "gasLevel": null
    },
    "statistics": {
      "totalItems": 2,
      "cardboard": 2,
      "paper": 0,
      "plastic_glass": 0,
      "metal": 0,
      "trash": 0,
      "recyclableItems": 2,
      "nonRecyclableItems": 0,
      "correctDisposals": 2,
      "incorrectDisposals": 0
    },
    "faults": {
      "camera": false,
      "ultrasonic": false,
      "network": false
    },
    "latestEvent": {
      "eventId": "%s",
      "timestamp": "%s",
      "label": "cardboard box",
      "category": "cardboard",
      "recyclable": true,
      "disposedSide": "recyclable",
      "expectedSide": "recyclable",
      "correct": true,
      "confidence": 0.91,
      "placementConfirmed": true,
      "modelVersion": "duplicate-test",
      "classificationSource": "camera",
      "imageUrl": null
    }
  }' "$ORG_ID" "$BIN_CODE" "$EVENT_ID" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}

post_once() {
  curl -sS -X POST "$SUPABASE_URL/functions/v1/ingest-bin-state" \
    -H "x-device-token: $TECHBIN_DEVICE_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(payload)"
}

printf 'First send with eventId %s:\n' "$EVENT_ID"
post_once
printf '\nSecond send with same eventId %s:\n' "$EVENT_ID"
post_once
printf '\n'
