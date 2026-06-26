# Firebase Cloud Pipeline

The frontend now connects to Firebase Cloud only. It does not connect to local emulators and does not poll for telemetry.

## Frontend Environment

Create `.env.local` from `.env.example` and fill the Firebase Web App values from Firebase Console > Project settings > Your apps > Web app config.

Required values:

```env
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=techbin-4c086.firebaseapp.com
VITE_FIREBASE_DATABASE_URL=https://techbin-4c086-default-rtdb.firebaseio.com
VITE_FIREBASE_PROJECT_ID=techbin-4c086
VITE_FIREBASE_STORAGE_BUCKET=techbin-4c086.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...
```

## Realtime Database Contract

The frontend listens at:

```text
orgs/{orgId}/bins/{binCode}
```

For the default TechBin organization and first bin, the Raspberry Pi should write:

```text
orgs/techbin/bins/BIN-001/state
```

Example payload:

```json
{
  "location": "Lab Bin",
  "status": {
    "state": "normal",
    "lastSeen": 1792579200000
  },
  "sensors": {
    "fillLevel": 43,
    "temperature": 29,
    "gasLevel": 12
  },
  "statistics": {
    "totalItems": 3,
    "plastic": 2,
    "recyclableItems": 2,
    "nonRecyclableItems": 1,
    "correctDisposals": 2,
    "incorrectDisposals": 1
  },
  "faults": {
    "ultrasonic": false,
    "camera": false,
    "ir": false,
    "metal": false,
    "network": false
  },
  "latestEvent": {
    "timestamp": 1792579200000,
    "label": "Plastic",
    "category": "Recyclable",
    "recyclable": true,
    "disposedSide": "Left",
    "expectedSide": "Right",
    "correct": false,
    "confidence": 94.7
  }
}
```

Optional event history can be appended under:

```text
orgs/{orgId}/bins/{binCode}/state/events/{eventId}
```

The frontend reads these events for the live monitoring table. The Pi remains responsible for model inference, disposal correctness, counters, and fault state.
