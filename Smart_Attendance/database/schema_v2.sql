-- SmartAttendance — Presence Tracking Schema (run after schema_v1.sql)
-- Adds check-in / check-out event log and live presence state.

-- 1. Presence log — every check-in and check-out event
create table if not exists presence_log (
    id          uuid primary key default gen_random_uuid(),
    person_id   uuid not null references persons(id),
    event_type  text not null check (event_type in ('checkin', 'checkout')),
    timestamp   timestamptz not null default now(),
    confidence  float,
    camera_id   text not null default 'main'
);
create index if not exists presence_log_person_idx    on presence_log(person_id);
create index if not exists presence_log_timestamp_idx on presence_log(timestamp desc);
create index if not exists presence_log_event_idx     on presence_log(event_type);

-- 2. Current status — one row per person, updated in real time
create table if not exists current_status (
    person_id   uuid primary key references persons(id),
    status      text not null default 'out' check (status in ('in', 'out')),
    last_seen   timestamptz,
    checkin_at  timestamptz,
    updated_at  timestamptz not null default now()
);

-- 3. Enable Supabase Realtime
do $$ begin
  alter publication supabase_realtime add table presence_log;
exception when duplicate_object then null;
end $$;

do $$ begin
  alter publication supabase_realtime add table current_status;
exception when duplicate_object then null;
end $$;

-- 4. Row Level Security
alter table presence_log    enable row level security;
alter table current_status  enable row level security;
create policy "backend full access" on presence_log   for all using (true) with check (true);
create policy "backend full access" on current_status for all using (true) with check (true);

-- 5. View: who is currently IN the building
create or replace view persons_currently_in as
select
    p.id,
    p.name,
    p.employee_id,
    p.department,
    cs.checkin_at,
    cs.last_seen,
    extract(epoch from (now() - cs.checkin_at))/3600 as hours_in
from persons p
join current_status cs on cs.person_id = p.id
where cs.status = 'in'
order by cs.checkin_at;
