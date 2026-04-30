-- SmartAttendance — Initial Schema
-- Run this first in Supabase SQL Editor (https://app.supabase.com -> SQL Editor)

-- 1. Enable pgvector extension
create extension if not exists vector;

-- 2. Persons (staff / students)
create table if not exists persons (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    employee_id text unique not null,
    email       text,
    department  text,
    created_at  timestamptz not null default now()
);

-- 3. Face embeddings  (512D from InsightFace ArcFace)
create table if not exists embeddings (
    id         uuid primary key default gen_random_uuid(),
    person_id  uuid not null references persons(id) on delete cascade,
    embedding  vector(512) not null,
    created_at timestamptz not null default now()
);
-- IVFFlat index for faster cosine search (rebuild after enrolling many people)
create index if not exists embeddings_vector_idx
    on embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 50);

-- 4. Unknown / unrecognized faces (for admin review)
create table if not exists unknown_faces (
    id              uuid primary key default gen_random_uuid(),
    timestamp       timestamptz not null default now(),
    face_image      text,       -- base64-encoded JPEG crop
    reviewed        boolean not null default false,
    reviewer_notes  text
);

-- 5. Enable Supabase Realtime
do $$ begin
  alter publication supabase_realtime add table unknown_faces;
exception when duplicate_object then null;
end $$;

-- 6. Row Level Security
alter table persons       enable row level security;
alter table embeddings    enable row level security;
alter table unknown_faces enable row level security;

create policy "backend full access" on persons       for all using (true) with check (true);
create policy "backend full access" on embeddings    for all using (true) with check (true);
create policy "backend full access" on unknown_faces for all using (true) with check (true);
