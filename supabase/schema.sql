-- CXO Movement Tracker — Supabase schema
-- Run once in Supabase Studio → SQL Editor.

create table if not exists public.moves (
  id            text primary key,            -- sha1(person|company|movement)
  date          date,
  person        text not null,
  movement      text not null,               -- Appointment | Promotion | Re-appointment | Resignation | Retirement
  role          text,
  role_group    text,                        -- CEO | MD | CFO | CMO | CDO | CHRO | … (see parser_lib.ROLE_GROUPS)
  company       text,
  moved_from    text,                        -- previous employer, when known
  moved_from_source text,                    -- headline | cross-reference | ''
  sector        text,                        -- BFSI | Pharma | Healthcare | Education | Corporate
  region        text,                        -- India | Global
  publisher     text,
  headline      text,
  link          text,
  also_reported_by jsonb default '[]',
  updated_at    timestamptz default now()
);

-- existing installs: `create table if not exists` above won't add new columns
alter table public.moves add column if not exists role_group text;

create index if not exists moves_sector_date on public.moves (sector, date desc);
create index if not exists moves_sector_role on public.moves (sector, role_group, date desc);
create index if not exists moves_region_date on public.moves (region, date desc);
create index if not exists moves_movement    on public.moves (movement);

-- NOTE: the public `moves_feed` view (source columns hidden) must be recreated
-- after adding a column, otherwise role_group will not reach API consumers:
--   create or replace view public.moves_feed as
--     select id, date, person, movement, role, role_group, company, moved_from,
--            moved_from_source, sector, region, headline from public.moves;

-- public, read-only API access (anon key can only SELECT)
alter table public.moves enable row level security;
drop policy if exists "public read" on public.moves;
create policy "public read" on public.moves for select using (true);
