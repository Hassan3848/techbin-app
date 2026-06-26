alter table public.bin_events
add column if not exists event_id text;

create unique index if not exists bin_events_bin_event_id_unique
on public.bin_events(bin_id, event_id);
