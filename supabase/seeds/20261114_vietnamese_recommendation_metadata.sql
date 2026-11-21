-- Vietnamese recommendation metadata. No audio, fingerprints or Spotify analytics.
-- Title/artist/year checked against MusicBrainz WM Vietnam release listing:
-- https://musicbrainz.org/label/8719da80-e6b5-4160-8ab3-913ba336c184
-- Core metadata license: https://musicbrainz.org/doc/About/Data_License (CC0).
-- Genre/mood tags are editorial examples, not MusicBrainz tags or trained predictions.
-- Existing catalog records are preserved. Run once or repeat without duplicates.
with supplied(title,artist,release_year,genres,moods) as (
  values
    ('Lạ Lùng','Vũ.',2016,array['indie','ballad','v-pop'],array['sad','chill','romantic']),
    ('Bước Qua Nhau','Vũ.',2021,array['ballad','v-pop'],array['sad','romantic']),
    ('Và Thế Là Hết','Chillies',2018,array['indie','pop','v-pop'],array['sad','chill']),
    ('Mascara','Chillies',2019,array['indie','ballad','v-pop'],array['sad','romantic']),
    ('Mặt Trời Của Em','Phương Ly',2017,array['pop','v-pop'],array['happy','romantic']),
    ('Yêu 5','Rhymastic',2017,array['pop','hip-hop','v-pop'],array['romantic','energetic']),
    ('Forever Alone','JustaTee',2013,array['r&b','hip-hop','v-pop'],array['sad','chill']),
    ('Missing You','Phương Ly',2020,array['pop','v-pop'],array['sad','romantic'])
)
insert into public.music_catalog
  (title,artist,release_year,genres,moods,tags,language,spotify_search_query,source,source_url,source_license)
select s.title,s.artist,s.release_year,s.genres,s.moods,array['editorial'],'vi',
       s.title || ' ' || s.artist,'MusicBrainz release listing',
       'https://musicbrainz.org/label/8719da80-e6b5-4160-8ab3-913ba336c184',
       'MusicBrainz core metadata CC0; genres/moods editorial; no audio rights included'
from supplied s
where not exists (
  select 1 from public.music_catalog c
  where lower(c.title)=lower(s.title) and lower(c.artist)=lower(s.artist)
)
returning id,title,artist,language;
