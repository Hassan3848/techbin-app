# TechBin Dashboard (Development Setup)

TechBin Dashboard is an internal organizational dashboard built for a Smart AI-based waste bin system.
It provides role-based access (Admin / Viewer), secure authentication, bin management, and live Raspberry Pi telemetry using Supabase.

---

## Tech Stack

Frontend:
- React + TypeScript
- Vite
- Tailwind CSS

Backend:
- Supabase Auth
- Supabase Postgres
- Supabase Realtime
- Supabase Edge Functions

---

## Project Structure

src/
 ├── app/
 │   ├── App.tsx
 │   ├── layouts/
 │   ├── providers/
 │   └── routing/
 ├── features/
 ├── shared/
 │   ├── supabase.ts
 │   └── ui/
 └── styles/

supabase/
 ├── schema.sql
 └── functions/

---

## Authentication & Roles

Roles:
- Admin: Can manage users and access all dashboard features
- Viewer: Read-only access

Permanent Root Admin:
admin@techbin.com

Create this user manually in Supabase Auth. When this user logs in, the app calls `bootstrap-admin-profile` to create/update the matching `profiles` row as Super Admin.

---

## How to Run the Project

From a fresh GitHub clone, run the setup script once:

```bash
chmod +x setup.sh
./setup.sh
```

```bash
./setup.sh dev
```

URLs:
- Frontend: http://localhost:5173

---

## One-Command Setup (Recommended for Sharing)

You can now bootstrap dependencies and verify the frontend build with one file:

- macOS / Linux:
  - Run:
    - `bash setup.sh`
  - Optional:
    - `chmod +x setup.sh && ./setup.sh`

- Windows (CMD):
  - Run:
    - `setup.bat`

What the setup scripts do:
- Check Node.js and package managers
- Install root dependencies (`pnpm`)
- Build the Vite frontend

After setup, create `.env.local` from `.env.example`, apply `supabase/schema.sql`, deploy the Supabase Edge Functions, then run `./setup.sh dev`.

---

## Best Way to Share This Project

Preferred:
- Share via GitHub/GitLab (small size, version history, easy updates)

If sharing a ZIP:
- Include:
  - project source files
  - `pnpm-lock.yaml`
  - `setup.sh` and `setup.bat`
- Exclude:
  - `node_modules`
  - `dist`

Then tell the receiver:
1. Extract ZIP
2. Run setup script (`setup.sh` or `setup.bat`)
3. Configure Supabase and run the frontend

---

## Create First Admin User

Open Supabase Dashboard > Authentication > Users and create:

Email: admin@techbin.com

Then login using the same credentials in the app.

---

## Creating More Users

Only Admin users can create new users using the User Management page.
Roles are enforced using the Supabase `profiles` table, RLS policies, and Edge Functions.

---

## Notes

- See `SUPABASE_PIPELINE.md` for the Pi ingest payload and first-bin setup.
- Analytics and telemetry pages read live Supabase tables once the Pi starts sending data.

---

If you follow these steps exactly, the project will run successfully.
