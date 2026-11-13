-- Music Discovery Vietnam: independent recommendation catalog and ad architecture.
-- Does not alter existing playlist/history tables and does not enable ad delivery.

create table if not exists public.music_catalog (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  artist text not null,
  album text,
  release_year integer check (release_year is null or release_year between 1900 and 2100),
  genres text[] not null default '{}',
  moods text[] not null default '{}',
  language text not null default 'other' check (language in ('vi','en','ko','ja','other')),
  spotify_search_query text not null,
  source text not null,
  source_url text,
  fingerprint_hashes text[] not null default '{}',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists music_catalog_active_idx on public.music_catalog(is_active, created_at desc);
create index if not exists music_catalog_genres_idx on public.music_catalog using gin(genres);
create index if not exists music_catalog_moods_idx on public.music_catalog using gin(moods);

create table if not exists public.user_music_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  genres text[] not null default '{}',
  moods text[] not null default '{}',
  languages text[] not null default '{}',
  updated_at timestamptz not null default now()
);

alter table public.music_catalog enable row level security;
alter table public.user_music_preferences enable row level security;
drop policy if exists "Active catalog is readable by authenticated users" on public.music_catalog;
create policy "Active catalog is readable by authenticated users" on public.music_catalog
  for select to authenticated using (is_active = true);
drop policy if exists "Users manage own music preferences" on public.user_music_preferences;
create policy "Users manage own music preferences" on public.user_music_preferences
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Advertisement architecture only. These tables are intentionally inaccessible to
-- end users and there is no serving endpoint or player integration in this release.
create table if not exists public.ad_campaigns (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'draft' check (status in ('draft','paused','approved','archived')),
  starts_at timestamptz,
  ends_at timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists public.ad_creatives (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references public.ad_campaigns(id) on delete cascade,
  format text not null check (format in ('banner','sponsored_card','audio')),
  asset_url text,
  destination_url text,
  duration_seconds integer check (duration_seconds is null or duration_seconds between 1 and 120),
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);
create table if not exists public.ad_placements (
  id uuid primary key default gen_random_uuid(),
  placement_key text not null unique,
  description text not null,
  enabled boolean not null default false,
  created_at timestamptz not null default now()
);
alter table public.ad_campaigns enable row level security;
alter table public.ad_creatives enable row level security;
alter table public.ad_placements enable row level security;
-- No policies are created: browser users cannot read or mutate ad operations data.
