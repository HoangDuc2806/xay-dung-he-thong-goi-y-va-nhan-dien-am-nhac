"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ExternalLink,
  LoaderCircle,
  Music2,
  RefreshCw,
  Search,
  Play,
} from "lucide-react";
import { ApiError, type SpotifyTrack } from "@/lib/api";
import { loadSpotifyBatch, mergeSpotifyTracks, type SpotifyBatch } from "@/lib/spotify-pages";
import { useSpotifyPlayer } from "@/components/spotify-player-provider";
import { TrackActions } from "@/components/track-actions";

type MusicCategory = {
  id: string;
  label: string;
  query: string;
  description: string;
};

const CATEGORIES: MusicCategory[] = [
  {
    id: "vietnam",
    label: "Nhạc Việt",
    query: "nhạc Việt",
    description: "Tìm các bài hát Việt Nam trong danh mục Spotify.",
  },
  {
    id: "vpop",
    label: "V-Pop",
    query: "V-Pop Việt Nam",
    description: "Nhạc pop Việt Nam và các ca khúc thịnh hành.",
  },
  {
    id: "rap",
    label: "Rap Việt",
    query: "Rap Việt",
    description: "Khám phá rap và hip-hop Việt Nam.",
  },
  {
    id: "chill",
    label: "Nhạc chill",
    query: "Vietnamese chill music",
    description: "Những lựa chọn nhẹ nhàng để học tập và thư giãn.",
  },
  {
    id: "kpop",
    label: "K-Pop",
    query: "K-pop",
    description: "Tìm các ca khúc K-Pop trong danh mục Spotify.",
  },
  {
    id: "global",
    label: "US-UK / Pop",
    query: "global pop hits",
    description: "Pop quốc tế và các bản hit phổ biến.",
  },
  { id: "rnb", label: "R&B", query: "genre:r&b", description: "Khám phá các bài R&B trên Spotify." },
  { id: "rock", label: "Rock", query: "genre:rock", description: "Khám phá các bài rock trên Spotify." },
  { id: "jazz", label: "Jazz", query: "genre:jazz", description: "Khám phá các bản jazz trên Spotify." },
  { id: "electronic", label: "Electronic", query: "genre:electronic", description: "Khám phá nhạc điện tử trên Spotify." },
];

function formatDuration(durationMs: number) {
  const seconds = Math.floor(Math.max(0, durationMs) / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function MusicLibrary() {
  const [categoryId, setCategoryId] = useState("vietnam");
  const [tracks, setTracks] = useState<SpotifyTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [playError, setPlayError] = useState("");
  const [reloadVersion, setReloadVersion] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState("");
  const cacheRef = useRef(new Map<string, SpotifyBatch>());
  const moreControllerRef = useRef<AbortController | null>(null);
  const morePendingRef = useRef(false);
  const moreButtonRef = useRef<HTMLButtonElement>(null);

  const {
    authorized,
    ready,
    currentTrack,
    playTrack,
    extendPlaybackQueue,
    connectSpotify,
  } = useSpotifyPlayer();

  const category = CATEGORIES.find((item) => item.id === categoryId) ?? CATEGORIES[0]!;
  const activeQueryRef = useRef(category.query);
  activeQueryRef.current = category.query;

  useEffect(() => {
    const controller = new AbortController();
    const cleanup = () => { controller.abort(); moreControllerRef.current?.abort(); };
    morePendingRef.current = false;
    setLoadingMore(false);
    setMoreError("");
    setPlayError("");
    const cached = cacheRef.current.get(category.query);
    if (cached) {
      setTracks(cached.items);
      setNextOffset(cached.next_offset);
      setMoreError(cached.warning);
      setLoading(false);
      setError("");
      return cleanup;
    }

    setTracks([]);
    setNextOffset(null);
    setLoading(true);
    setError("");
    setPlayError("");

    void loadSpotifyBatch(category.query, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        cacheRef.current.set(category.query, response);
        setTracks(response.items);
        setNextOffset(response.next_offset);
        setMoreError(response.warning);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setTracks([]);
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Không thể tải kho nhạc Spotify lúc này. Hãy thử lại."
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return cleanup;
  }, [category.query, reloadVersion]);

  const loadMore = useCallback(async () => {
    if (nextOffset === null || morePendingRef.current || loading) return;
    const query = category.query;
    const controller = new AbortController();
    moreControllerRef.current = controller;
    morePendingRef.current = true;
    setLoadingMore(true);
    setMoreError("");
    try {
      const result = await loadSpotifyBatch(query, controller.signal, nextOffset);
      if (controller.signal.aborted || activeQueryRef.current !== query) return;
      const previous = cacheRef.current.get(query)?.items ?? tracks;
      const merged = mergeSpotifyTracks(previous, result.items);
      extendPlaybackQueue(previous, merged);
      cacheRef.current.set(query, { ...result, items: merged });
      setTracks(merged);
      setNextOffset(result.next_offset);
      setMoreError(result.warning);
    } catch (caught) {
      if (!controller.signal.aborted && activeQueryRef.current === query) {
        setMoreError(caught instanceof Error ? caught.message : "Không tải thêm được bài hát. Hãy thử lại.");
      }
    } finally {
      if (!controller.signal.aborted && activeQueryRef.current === query) {
        morePendingRef.current = false;
        setLoadingMore(false);
      }
    }
  }, [nextOffset, loading, category.query, tracks, extendPlaybackQueue]);

  useEffect(() => {
    const button = moreButtonRef.current;
    if (!button || loading || loadingMore || moreError || !window.IntersectionObserver) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) void loadMore();
    }, { rootMargin: "240px" });
    observer.observe(button);
    return () => observer.disconnect();
  }, [loading, loadingMore, moreError, loadMore]);

  async function handlePlay(track: SpotifyTrack) {
    setPlayError("");

    if (!authorized) {
      connectSpotify(window.location.pathname + window.location.search);
      return;
    }

    if (!ready) {
      setPlayError("Spotify đã cấp quyền nhưng trình phát chưa sẵn sàng. Hãy đợi vài giây rồi thử lại.");
      return;
    }

    try {
      await playTrack(track, tracks);
    } catch (caught: unknown) {
      setPlayError(
        caught instanceof Error
          ? caught.message
          : "Không thể phát bài hát trên Spotify. Hãy thử lại."
      );
    }
  }

  function reloadCategory() {
    moreControllerRef.current?.abort();
    cacheRef.current.delete(category.query);
    setReloadVersion((value) => value + 1);
  }

  return (
    <div id="music-catalog" className="space-y-5 scroll-mt-28">
      <section className="mb-2">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="eyebrow mb-2 text-lime-400">Tìm giai điệu của bạn</p>
            <h2 className="text-[23px] font-semibold tracking-tight">Cho tâm trạng hôm nay</h2>
            <p className="mt-2 text-[13px] leading-relaxed text-mist-300">
              {category.description}
            </p>
            <p className="mt-2 text-xs text-mist-400">
              {authorized
                ? ready
                  ? "Spotify đã kết nối · Có thể phát trên website"
                  : "Đã cấp quyền Spotify · Đang khởi tạo trình phát"
                : "Có thể xem danh mục; cần kết nối Spotify Premium để phát trực tiếp trên website."}
            </p>
          </div>
          <a
            href="/search"
            className="hidden shrink-0 items-center gap-2 rounded-full border border-white/10 px-4 py-2.5 text-xs font-medium text-mist-300 hover:border-lime-500 hover:text-lime-300 sm:inline-flex"
          >
            <Search size={14} /> Tìm kiếm
          </a>
        </div>
      </section>

      <div className="flex flex-wrap gap-2" aria-label="Chọn thể loại nhạc">
        {CATEGORIES.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={categoryId === item.id}
            onClick={() => setCategoryId(item.id)}
            className={`rounded-full border px-4 py-2.5 text-xs font-medium transition ${
              categoryId === item.id
                ? "border-lime-400 bg-lime-400 text-ink-950"
                : "border-white/[0.06] bg-ink-900/70 text-mist-300 hover:border-ink-500 hover:text-mist-100"
            }`}
          >
            {item.label}
          </button>
        ))}
        <button
          type="button"
          onClick={reloadCategory}
          disabled={loading || loadingMore}
          className="ml-auto inline-flex items-center gap-2 rounded-full border border-ink-700 px-3 py-2 text-sm text-mist-300 hover:border-ink-500 disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Tải lại
        </button>
      </div>

      {playError && (
        <div role="alert" className="rounded-xl border border-red-800/70 bg-red-950/30 p-4 text-sm text-red-200">
          {playError}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-3 rounded-xl border border-ink-700 bg-ink-900 p-6 text-sm text-mist-300">
          <LoaderCircle size={18} className="animate-spin" />
          Đang tải bài hát từ Spotify…
        </div>
      )}

      {!loading && error && (
        <div role="alert" className="rounded-xl border border-red-800/70 bg-red-950/30 p-5 text-sm text-red-200">
          <p>{error}</p>
          <button type="button" onClick={reloadCategory} className="mt-3 rounded-lg border border-red-700 px-3 py-2 font-medium hover:bg-red-900/40">
            Thử lại
          </button>
        </div>
      )}

      {!loading && !error && tracks.length === 0 && (
        <div className="rounded-xl border border-dashed border-ink-700 p-8 text-center">
          <Music2 size={28} className="mx-auto mb-3 text-mist-400" />
          <p className="font-medium">Chưa tìm thấy bài hát trong mục này</p>
          <p className="mt-1 text-sm text-mist-300">Chọn thể loại khác hoặc thử tìm kiếm tên bài hát cụ thể.</p>
        </div>
      )}

      {!loading && !error && tracks.length > 0 && (
        <section aria-label={`Bài hát: ${category.label}`}>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold">{category.label} <span className="ml-2 text-xs font-normal text-mist-400">{tracks.length} bài hát</span></h3>
              <p className="mt-1 text-xs text-mist-400">Khám phá từ danh mục Spotify</p>
            </div>
            <a href="https://open.spotify.com/" target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-xs font-semibold text-mist-300 hover:text-lime-400">
              Spotify <ExternalLink size={13} />
            </a>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 sm:gap-4">
            {tracks.map((track) => {
              const isCurrentTrack = currentTrack?.uri === track.uri;
              const releaseYear = track.release_date?.slice(0, 4);

              return (
                <article
                  key={track.id}
                  className={`catalog-card group ${isCurrentTrack ? "is-current" : ""}`}
                >
                  <div className="cover-wrap">
                    {track.album_image_url ? (
                      <img
                        src={track.album_image_url}
                        alt={`Ảnh bìa ${track.album_name ?? track.name}`}
                        loading="lazy"
                        width={300}
                        height={300}
                      />
                    ) : (
                      <div className="grid h-full place-items-center bg-gradient-to-br from-[#3b304c] to-[#24232d] text-lime-300/60">
                        <Music2 size={48} strokeWidth={1} aria-hidden />
                      </div>
                    )}
                    <button type="button" onClick={() => void handlePlay(track)} className="cover-play"
                      aria-label={`${!authorized ? "Kết nối Spotify để phát" : "Phát"} ${track.name}`} title={`Phát ${track.name}`}>
                      <Play size={19} fill="currentColor" className="ml-0.5" />
                    </button>
                    {isCurrentTrack && <span className="absolute left-2.5 top-2.5 z-[1] rounded-md bg-black/70 px-2 py-1 text-[9px] font-semibold tracking-wide text-lime-300 backdrop-blur">ĐANG CHỌN</span>}
                  </div>
                    <div className="min-w-0 px-0.5 pb-1 pt-3">
                      <h4 className="truncate text-[13px] font-semibold leading-snug sm:text-sm" title={track.name}>{track.name}</h4>
                      <p className="mt-1 truncate text-[11px] text-mist-300 sm:text-xs" title={track.artists.join(", ")}>
                        {track.artists.join(", ") || "Chưa rõ nghệ sĩ"}
                      </p>
                      <p className="mt-2 truncate text-xs text-mist-400">
                        {releaseYear ? `${releaseYear} · ` : ""}{formatDuration(track.duration_ms)}
                      </p>
                    </div>
                  <div className="track-utilities mt-2 flex items-center gap-1 border-t border-white/[0.05] pt-2">
                    <TrackActions track={track} />
                    <a
                      href={track.spotify_url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-auto inline-flex items-center justify-center gap-1 text-[9px] text-mist-400 hover:text-lime-300 sm:text-[10px]"
                      aria-label={`Mở ${track.name} trên Spotify`}
                    >
                      Spotify <ExternalLink size={13} />
                    </a>
                  </div>
                </article>
              );
            })}
          </div>
          {moreError && <p role="alert" className="mt-4 rounded-lg border border-amber-700 p-3 text-sm text-amber-200">{moreError}</p>}
          {nextOffset !== null && <div className="mt-6 text-center">
            <button ref={moreButtonRef} type="button" onClick={() => void loadMore()} disabled={loadingMore}
              className="inline-flex items-center gap-2 rounded-full border border-lime-500 px-6 py-3 text-sm font-semibold text-lime-300 hover:bg-lime-400/10 disabled:opacity-50">
              {loadingMore && <LoaderCircle size={16} className="animate-spin" />}
              {loadingMore ? "Đang tải thêm…" : "Tải thêm bài hát"}
            </button>
          </div>}
        </section>
      )}

      <p className="text-xs leading-relaxed text-mist-400">
        Dữ liệu bài hát và ảnh bìa được lấy từ Spotify, có liên kết mở bản gốc. Music Discovery Vietnam không tải xuống hoặc lưu trữ tệp âm thanh Spotify. Phát trực tiếp yêu cầu tài khoản Spotify Premium và quyền truy cập phù hợp.
      </p>
    </div>
  );
}
