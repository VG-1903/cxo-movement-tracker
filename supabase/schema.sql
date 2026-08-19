-- CXO Movement Tracker — Supabase schema
-- Run once in Supabase Studio → SQL Editor.

create table if not exists public.moves (
  id            text primary key,            -- sha1(person|company|movement)
  date          date,
  person        text not null,
  movement      text not null,               -- Appointment | Promotion | Re-appointment | Resignation | Retirement
  role          text,
  company       text,
  sector        text,                        -- BFSI | Education | Pharma & Healthcare | Corporate
  region        text,                        -- India | Global
  publisher     text,
  headline      text,
  link          text,
  also_reported_by jsonb default '[]',
  updated_at    timestamptz default now()
);

create index if not exists moves_sector_date on public.moves (sector, date desc);
create index if not exists moves_region_date on public.moves (region, date desc);
create index if not exists moves_movement    on public.moves (movement);

-- public, read-only API access (anon key can only SELECT)
alter table public.moves enable row level security;
drop policy if exists "public read" on public.moves;
create policy "public read" on public.moves for select using (true);
