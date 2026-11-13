-- Upgrade for Music Discovery Vietnam; apply once AFTER existing Phase 2/3 migrations.
-- Does not alter or remove existing playlist and Spotify storage tables.
create extension if not exists pgcrypto;

create table if not exists public.music_catalog(
 id uuid primary key default gen_random_uuid(),
 title text not null check(length(trim(title))>0),
 artist text not null check(length(trim(artist))>0),
 album text,
 release_year integer check (release_year is null or release_year between 1600 and 2100),
 genres text[] not null default '{}',
 moods text[] not null default '{}',
 tags text[] not null default '{}',
 language text not null default 'other',
 artwork_url text,
 spotify_search_query text not null,
 source text not null check(length(trim(source))>0),
 source_url text not null check(source_url ~ '^https://'),
 source_license text not null check(length(trim(source_license))>0),
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
drop trigger if exists music_catalog_updated_at on public.music_catalog;
create trigger music_catalog_updated_at before update on public.music_catalog
for each row execute function public.set_updated_at();
create index if not exists music_catalog_genres_gin on public.music_catalog using gin(genres);
create index if not exists music_catalog_moods_gin on public.music_catalog using gin(moods);
create index if not exists music_catalog_active_time on public.music_catalog(is_active,created_at desc);

create table if not exists public.user_music_preferences(
 user_id uuid primary key references auth.users(id) on delete cascade,
 genres text[] not null default '{}',
 moods text[] not null default '{}',
 languages text[] not null default '{}',
 artists text[] not null default '{}',
 blocked_artists text[] not null default '{}',
 discovery_level smallint not null default 50 check(discovery_level between 0 and 100),
 updated_at timestamptz not null default now()
);
drop trigger if exists music_preferences_updated_at on public.user_music_preferences;
create trigger music_preferences_updated_at before update on public.user_music_preferences
for each row execute function public.set_updated_at();

create table if not exists public.user_music_feedback(
 user_id uuid not null references auth.users(id) on delete cascade,
 track_id uuid not null references public.music_catalog(id) on delete cascade,
 action text not null check(action in ('like','dislike','save','skip')),
 updated_at timestamptz not null default now(),
 primary key(user_id,track_id)
);
drop trigger if exists music_feedback_updated_at on public.user_music_feedback;
create trigger music_feedback_updated_at before update on public.user_music_feedback
for each row execute function public.set_updated_at();

create table if not exists public.recognition_history(
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 status text not null check(status in ('matched','not_found')),
 duration_seconds integer not null check(duration_seconds>=0),
 results jsonb not null default '[]',
 created_at timestamptz not null default now()
);
create index if not exists recognition_history_user_idx on public.recognition_history(user_id,created_at desc);

-- Landmark points are generated ONLY from audio authorized for fingerprint indexing.
-- No direct browser SELECT or INSERT on this table.
create table if not exists public.music_fingerprint_points(
 track_id uuid not null references public.music_catalog(id) on delete cascade,
 hash text not null check(length(hash)=16),
 offset_ms integer not null check(offset_ms >= 0),
 algorithm text not null default 'mdvn-landmark-v2',
 primary key(track_id,hash,offset_ms,algorithm)
);
create index if not exists music_landmark_lookup_idx on public.music_fingerprint_points(hash,algorithm);

-- Scoped, bounded matching through RPC; does not expose the fingerprint index to users.
create or replace function public.match_audio_landmarks(query_hashes text[],query_offsets integer[])
returns table(title text,artist text,album text,release_year integer,votes bigint,score numeric)
language plpgsql security definer set search_path=''
as $$
begin
 if auth.uid() is null then
   raise exception 'Authentication required';
 end if;
 if query_hashes is null or query_offsets is null
    or cardinality(query_hashes) <> cardinality(query_offsets)
    or cardinality(query_hashes) > 400 then
   raise exception 'Invalid fingerprint query';
 end if;
 return query
 with incoming as (
   select distinct x.hash,x.offset_ms
   from unnest(query_hashes,query_offsets) as x(hash,offset_ms)
   where length(x.hash)=16 and x.offset_ms between 0 and 3600000
 ), histogram as (
   select p.track_id,
     (round((p.offset_ms-i.offset_ms)::numeric/125)*125)::integer as shift,
     count(distinct p.hash)::bigint as number
   from incoming i join public.music_fingerprint_points p on p.hash=i.hash and p.algorithm='mdvn-landmark-v2'
   group by p.track_id,shift
 ), best as (
   select h.track_id,max(h.number) as number
   from histogram h group by h.track_id
 )
 select c.title,c.artist,c.album,c.release_year,b.number,
   least(1.0,b.number::numeric / greatest(10,cardinality(query_hashes))) as score
 from best b join public.music_catalog c on c.id=b.track_id
 where b.number>=7 and c.is_active=true
 order by b.number desc limit 5;
end;
$$;
revoke all on function public.match_audio_landmarks(text[],integer[]) from public,anon;
grant execute on function public.match_audio_landmarks(text[],integer[]) to authenticated;

alter table public.music_catalog enable row level security;
alter table public.user_music_preferences enable row level security;
alter table public.user_music_feedback enable row level security;
alter table public.recognition_history enable row level security;
alter table public.music_fingerprint_points enable row level security;
revoke all on public.music_fingerprint_points from public,anon,authenticated;

grant select on public.music_catalog to authenticated;
grant select,insert,update on public.user_music_preferences to authenticated;
grant select,insert,update on public.user_music_feedback to authenticated;
grant select,insert on public.recognition_history to authenticated;

drop policy if exists "catalog_active_read" on public.music_catalog;
create policy "catalog_active_read" on public.music_catalog for select to authenticated using (is_active=true);
drop policy if exists "music_preferences_own" on public.user_music_preferences;
create policy "music_preferences_own" on public.user_music_preferences for all to authenticated
 using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "music_feedback_own" on public.user_music_feedback;
create policy "music_feedback_own" on public.user_music_feedback for all to authenticated
 using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "recognition_history_own" on public.recognition_history;
create policy "recognition_history_own" on public.recognition_history for all to authenticated
 using(auth.uid()=user_id) with check(auth.uid()=user_id);

-- Only placeholder architecture. Not served by any API and RLS deny-by-default.
create table if not exists public.ad_campaigns(
 id uuid primary key default gen_random_uuid(),
 title text not null,
 status text not null default 'draft' check(status in ('draft','paused','archived')),
 created_at timestamptz not null default now()
);
create table if not exists public.ad_creatives(
 id uuid primary key default gen_random_uuid(),
 campaign_id uuid not null references public.ad_campaigns(id) on delete cascade,
 creative_type text not null check(creative_type in ('banner','sponsored_card','audio')),
 asset_url text,
 created_at timestamptz not null default now()
);
create table if not exists public.ad_placements(
 id uuid primary key default gen_random_uuid(),
 location_key text unique not null,
 enabled boolean not null default false
);
alter table public.ad_campaigns enable row level security;
alter table public.ad_creatives enable row level security;
alter table public.ad_placements enable row level security;
-- No policies, no grants, no ad-serving route: ads remain disabled.
