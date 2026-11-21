"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, ArrowUpRight, Mic, Music2, Pause, Play } from "lucide-react";
import { searchSpotifyTracks, type SpotifyTrack } from "@/lib/api";
import { useSpotifyPlayer } from "./spotify-player-provider";
import { TrackActions } from "./track-actions";

function HomeCollection({ title, query, compact = false }: { title: string; query: string; compact?: boolean }) {
  const feed = useQuery({
    queryKey: ["home-collection", query], queryFn: ({ signal }) => searchSpotifyTracks(query, signal),
    staleTime: 10 * 60_000, retry: false, refetchOnWindowFocus: false,
  });
  const { playTrack, authorized, connectSpotify, currentTrack, paused, togglePlayback } = useSpotifyPlayer();
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const rail = useRef<HTMLDivElement>(null);
  const items = feed.data?.items ?? [];
  // Lead genre shelves with different artists, keeping every track available.
  const seen = new Set<string>();
  const first: SpotifyTrack[] = [], rest: SpotifyTrack[] = [];
  for (const item of items) {
    const artist = item.artists[0] ?? item.id;
    (seen.has(artist) ? rest : first).push(item);
    seen.add(artist);
  }
  const tracks = compact ? items : [...first, ...rest];
  const featured = tracks[0];
  const isPlaying = (track: SpotifyTrack) => currentTrack?.uri === track.uri && !paused;
  async function play(track: SpotifyTrack) {
    if (!authorized) { connectSpotify("/"); return; }
    setError("");
    try {
      if (currentTrack?.uri === track.uri) await togglePlayback();
      else await playTrack(track, tracks);
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Không phát được bài."); }
  }

  return <section className="home-collection" aria-label={title}>
    {!compact && <header className="shelf-heading">
      <h2 className="mr-auto text-lg font-bold tracking-tight sm:text-xl">{title}</h2>
      {tracks.length > 0 && <button type="button" className="shelf-expand" aria-expanded={expanded}
        onClick={() => setExpanded(value => !value)}>{expanded ? "Thu gọn" : "Xem tất cả"}</button>}
      {!expanded && tracks.length > 0 && ([-1, 1] as const).map(direction =>
        <button key={direction} type="button" aria-label={direction === 1 ? `Xem thêm ${title}` : `Quay lại ${title}`}
          className="rounded-full border border-white/10 p-2 hover:bg-ink-700"
          onClick={() => { const el = rail.current; if (el) el.scrollBy({ left: direction * el.clientWidth * .85, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }}>
          {direction === 1 ? <ArrowRight size={15} /> : <ArrowLeft size={15} />}
        </button>)}
    </header>}
    {feed.isPending ? <p role="status" className="text-sm text-mist-400">Đang tải bài hát…</p>
      : feed.isError ? <div role="alert" className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm">
          <p className="text-mist-300">{feed.error instanceof Error ? feed.error.message : "Chưa tải được danh sách bài hát."}</p>
          <button type="button" disabled={feed.isFetching} onClick={() => void feed.refetch()}
            className="mt-3 rounded-full border border-white/15 px-4 py-2 text-lime-300 disabled:opacity-50">
            {feed.isFetching ? "Đang tải lại…" : `Tải lại mục ${title}`}
          </button>
        </div>
      : !tracks.length ? <p className="text-sm text-mist-400">Chưa có bài trong mục này.</p> :
      <div className={compact ? "artist-layout" : undefined}>
        {compact && featured && <article className="featured-record">
          <div className="record-sleeve">
            <div className="record-disc" aria-hidden="true" />
            {featured.album_image_url ? <img src={featured.album_image_url} alt={`Ảnh bìa ${featured.name}`} /> : <Music2 size={58} />}
          </div>
          <div className="featured-details">
            <p>{featured.artists.join(" · ")}</p>
            <h2>{featured.name}</h2>
            <div className="featured-buttons">
              <button onClick={() => void play(featured)}>{isPlaying(featured) ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
                {isPlaying(featured) ? "Tạm dừng" : "Phát ngay"}</button>
              <a href={featured.spotify_url} target="_blank" rel="noreferrer">Spotify <ArrowUpRight size={16} /></a>
              <TrackActions track={featured} queueOnly />
            </div>
          </div>
        </article>}
        <div className={compact ? "quick-panel" : undefined}>
        {compact && <h2>{title}</h2>}
        <div ref={rail} className={compact ? "quick-tracks" : expanded ? "music-rail shelf-grid" : "music-rail"}>
        {(compact ? tracks.slice(1) : tracks).map(track => <article key={track.id} className={compact ? "quick-track" : "rail-track"}>
          <button type="button" onClick={() => void play(track)} aria-label={`${isPlaying(track) ? "Tạm dừng" : "Phát"} ${track.name} — ${track.artists.join(", ")}`}>
            <span className="art">
              {track.album_image_url ? <img src={track.album_image_url} loading="lazy" alt="" /> : <Music2 />}
              <span className={`rail-play ${isPlaying(track) ? "playing" : ""}`}>{isPlaying(track) ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}</span>
            </span>
            <span className="block min-w-0"><strong className="block truncate text-sm">{track.name}</strong>
              <span className="block truncate text-xs text-mist-300">{track.artists.join(", ")}</span></span>
          </button>
          {!compact && <div className="track-utilities flex items-center gap-1"><TrackActions track={track} />
            <a className="ml-auto text-[10px] text-mist-400" href={track.spotify_url} target="_blank" rel="noreferrer">Spotify ↗</a></div>}
          {compact && <div className="quick-actions"><TrackActions track={track} queueOnly />
            <a href={track.spotify_url} target="_blank" rel="noreferrer" aria-label={`Mở ${track.name} trên Spotify`} className="px-1 text-xs text-mist-400">↗</a></div>}
        </article>)}
        </div>
        </div>
      </div>}
    {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
  </section>;
}

export function HomeHero() {
  return <div className="home-feed">
    <header className="listen-heading flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-3xl font-bold tracking-tight">Nghe ngay</h1>
      <Link href="/identify" className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm"><Mic size={15} />Nhận diện bài hát</Link>
    </header>
    <HomeCollection title="B Ray · Chọn nhanh" query={'artist:"B Ray"'} compact />
    <HomeCollection title="Indie pop" query="genre:indie pop" />
    <HomeCollection title="R&B" query="genre:r&b" />
  </div>;
}
