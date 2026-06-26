# Supabase Pipeline

The frontend uses Supabase Auth, Postgres, and Realtime. Raspberry Pi telemetry is accepted through the `ingest-bin-state` Edge Function, not by direct client table writes.

## Environment

Create `.env.local` from `.env.example`:

```bash
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=replace-with-supabase-anon-key
```

Edge Functions need these secrets:

```bash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY (set this only in Supabase Function Secrets)
TECHBIN_ROOT_ADMIN_EMAIL=admin@techbin.com
TECHBIN_ROOT_ORG_ID=techbin
```

## Database Setup

Run `supabase/schema.sql` in the Supabase SQL editor. It creates:

- `profiles`
- `user_settings`
- `bins`
- `bin_states`
- `bin_events`
- `pi_devices`

It also enables RLS and Realtime for the live dashboard tables.

## First Admin

1. Create `admin@techbin.com` manually in Supabase Auth.
2. Log in once from the web app.
3. The `bootstrap-admin-profile` Edge Function creates/updates its profile as:
   - `role = Admin`
   - `org_id = techbin`
   - `super_admin = true`

If you prefer manual SQL, insert the matching row in `profiles` yourself.

## Pi Contract

For the one-bin demo, provision:

- `org_id = techbin`
- `bin_code = BIN-001`
- `id = techbin_BIN-001`

The Pi sends:

```http
POST /functions/v1/ingest-bin-state
x-device-token: <device-token>
```

Example body:

```json
{
  "orgId": "techbin",
  "binCode": "BIN-001",
  "status": { "state": "normal" },
  "sensors": { "fillLevel": 42, "temperature": 31, "gasLevel": 10 },
  "statistics": { "totalItems": 12, "recyclableItems": 8, "nonRecyclableItems": 4 },
  "faults": { "camera": false, "gas": false },
  "latestEvent": {
    "label": "plastic bottle",
    "category": "plastic",
    "recyclable": true,
    "disposedSide": "recyclable",
    "expectedSide": "recyclable",
    "correct": true,
    "confidence": 0.93
  }
}
```

Store only the SHA-256 hash of the device token in `pi_devices.token_hash`.
