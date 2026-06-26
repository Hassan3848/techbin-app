create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  display_name text,
  role text not null check (role in ('Admin', 'Viewer')),
  org_id text not null,
  super_admin boolean not null default false,
  disabled boolean not null default false,
  created_at timestamptz not null default now(),
  created_by text,
  updated_at timestamptz,
  updated_by text
);

create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  org_id text not null,
  refresh_rate text not null default '10',
  session_timeout text not null default '30',
  theme text not null default 'light' check (theme in ('light', 'dark')),
  notifications boolean not null default true,
  created_at timestamptz not null default now(),
  created_by text,
  updated_at timestamptz,
  updated_by text
);

create table if not exists public.bins (
  id text primary key,
  org_id text not null,
  bin_code text not null,
  location text,
  status text not null default 'Active' check (status in ('Active', 'Maintenance', 'Inactive')),
  capacity_liters numeric,
  created_at timestamptz not null default now(),
  created_by text,
  updated_at timestamptz,
  updated_by text,
  unique (org_id, bin_code)
);

create table if not exists public.bin_states (
  bin_id text primary key references public.bins(id) on delete cascade,
  org_id text not null,
  bin_code text not null,
  status jsonb not null default '{}'::jsonb,
  sensors jsonb not null default '{}'::jsonb,
  statistics jsonb not null default '{}'::jsonb,
  faults jsonb not null default '{}'::jsonb,
  latest_event jsonb,
  last_seen timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.bin_events (
  id uuid primary key default gen_random_uuid(),
  bin_id text not null references public.bins(id) on delete cascade,
  org_id text not null,
  bin_code text not null,
  timestamp timestamptz not null default now(),
  label text,
  category text,
  recyclable boolean,
  disposed_side text,
  expected_side text,
  correct boolean,
  confidence numeric,
  image_url text,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.pi_devices (
  id uuid primary key default gen_random_uuid(),
  bin_id text not null references public.bins(id) on delete cascade,
  org_id text not null,
  bin_code text not null,
  device_name text not null,
  token_hash text not null,
  active boolean not null default true,
  last_seen timestamptz,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.user_settings enable row level security;
alter table public.bins enable row level security;
alter table public.bin_states enable row level security;
alter table public.bin_events enable row level security;
alter table public.pi_devices enable row level security;

create or replace function public.current_profile()
returns public.profiles
language sql
stable
security definer
set search_path = public
as $$
  select * from public.profiles where id = auth.uid() and disabled = false limit 1
$$;

create or replace function public.current_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(select 1 from public.profiles where id = auth.uid() and disabled = false and role = 'Admin')
$$;

create or replace function public.current_is_super_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(select 1 from public.profiles where id = auth.uid() and disabled = false and super_admin = true)
$$;

create policy "profiles admin scoped read"
on public.profiles for select
to authenticated
using (
  public.current_is_super_admin()
  or (
    public.current_is_admin()
    and org_id = (select org_id from public.current_profile())
  )
  or id = auth.uid()
);

create policy "settings owner read"
on public.user_settings for select
to authenticated
using (user_id = auth.uid());

create policy "settings owner upsert"
on public.user_settings for insert
to authenticated
with check (user_id = auth.uid());

create policy "settings owner update"
on public.user_settings for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create policy "bins scoped read"
on public.bins for select
to authenticated
using (
  public.current_is_super_admin()
  or org_id = (select org_id from public.current_profile())
);

create policy "bins super admin create"
on public.bins for insert
to authenticated
with check (public.current_is_super_admin());

create policy "bins admin scoped update"
on public.bins for update
to authenticated
using (
  public.current_is_super_admin()
  or (public.current_is_admin() and org_id = (select org_id from public.current_profile()))
)
with check (
  public.current_is_super_admin()
  or (public.current_is_admin() and org_id = (select org_id from public.current_profile()))
);

create policy "bins super admin delete"
on public.bins for delete
to authenticated
using (public.current_is_super_admin());

create policy "bin states scoped read"
on public.bin_states for select
to authenticated
using (
  public.current_is_super_admin()
  or org_id = (select org_id from public.current_profile())
);

create policy "bin events scoped read"
on public.bin_events for select
to authenticated
using (
  public.current_is_super_admin()
  or org_id = (select org_id from public.current_profile())
);

create policy "pi devices super admin read"
on public.pi_devices for select
to authenticated
using (public.current_is_super_admin());

create index if not exists profiles_org_created_idx on public.profiles(org_id, created_at desc);
create index if not exists bins_org_created_idx on public.bins(org_id, created_at desc);
create index if not exists bin_events_bin_timestamp_idx on public.bin_events(bin_id, timestamp desc);

alter publication supabase_realtime add table public.bins;
alter publication supabase_realtime add table public.bin_states;
alter publication supabase_realtime add table public.bin_events;
