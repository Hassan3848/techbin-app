#!/usr/bin/env bash
set -Eeuo pipefail

SUPABASE_URL="${VITE_SUPABASE_URL:-https://oqafmtuhfpapolylxvht.supabase.co}"
ORG_ID="${TECHBIN_ORG_ID:-techbin}"
BIN_CODE="${TECHBIN_BIN_CODE:-BIN-001}"
EVENT_ID="${TECHBIN_EVENT_ID:-manual-$(date -u +"%Y%m%dT%H%M%SZ")}"

if [[ -z "${TECHBIN_DEVICE_TOKEN:-}" ]]; then
  printf 'TECHBIN_DEVICE_TOKEN is required.\n' >&2
  printf 'Generate a Pi token in the dashboard, then run:\n' >&2
  printf '  TECHBIN_DEVICE_TOKEN=tb_pi_... pnpm test:pi-ingest\n' >&2
  exit 1
fi

curl -sS -X POST "$SUPABASE_URL/functions/v1/ingest-bin-state" \
  -H "x-device-token: $TECHBIN_DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"orgId\": \"$ORG_ID\",
    \"binCode\": \"$BIN_CODE\",
    \"status\": {
      \"state\": \"normal\",
      \"message\": \"Manual web-side ingest test\"
    },
    \"sensors\": {
      \"leftFillLevel\": 38,
      \"rightFillLevel\": 61,
      \"fillLevel\": 61,
      \"temperature\": null,
      \"gasLevel\": null
    },
    \"statistics\": {
      \"totalItems\": 1,
      \"cardboard\": 1,
      \"paper\": 0,
      \"plastic_glass\": 0,
      \"metal\": 0,
      \"trash\": 0,
      \"recyclableItems\": 1,
      \"nonRecyclableItems\": 0,
      \"correctDisposals\": 1,
      \"incorrectDisposals\": 0
    },
    \"faults\": {
      \"camera\": false,
      \"ultrasonic\": false,
      \"network\": false
    },
    \"latestEvent\": {
      \"eventId\": \"$EVENT_ID\",
      \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\",
      \"label\": \"cardboard box\",
      \"category\": \"cardboard\",
      \"recyclable\": true,
      \"disposedSide\": \"recyclable\",
      \"expectedSide\": \"recyclable\",
      \"correct\": true,
      \"confidence\": 0.91,
      \"placementConfirmed\": true,
      \"modelVersion\": \"manual-test\",
      \"classificationSource\": \"camera\",
      \"imageUrl\": null
    }
  }"

printf '\n'
