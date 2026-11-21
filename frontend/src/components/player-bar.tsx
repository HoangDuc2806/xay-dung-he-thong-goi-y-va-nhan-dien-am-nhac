
"use client";

import { useState } from "react";
import {
  Music2,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
} from "lucide-react";
import { useSpotifyPlayer } from "@/components/spotify-player-provider";
import { PlaybackQueue } from "./playback-queue";

function formatTime(milliseconds: number) {
  const seconds = Math.floor(Math.max(0, milliseconds) / 1000);

  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function PlayerBar() {
  const {
    configured,
    authorized,
    ready,
    currentTrack,
    paused,
    position,
    duration,
    volume,
    error,
    connectSpotify,
    togglePlayback,
    nextTrack,
    previousTrack,
    canSkipNext,
    canSkipPrevious,
    seekTo,
    setVolume,
  } = useSpotifyPlayer();

  const btn =
    "rounded-full p-2 text-mist-300 transition hover:bg-ink-700 hover:text-mist-100 disabled:cursor-not-allowed disabled:opacity-40";

  const canControl =
    authorized && ready && Boolean(currentTrack);

  // Vị trí tạm thời khi người dùng đang kéo thanh tiến trình.
  const [seekPreview, setSeekPreview] = useState<number | null>(null);

  const maxPosition = Math.max(
    1,
    duration || currentTrack?.durationMs || 1
  );

  const displayedPosition = Math.max(
    0,
    Math.min(seekPreview ?? position, maxPosition)
  );

  const commitSeek = (value: number) => {
    setSeekPreview(null);

    void seekTo(value).catch(() => undefined);
  };

  return (
    <div
      role="region"
      aria-label="Trình phát Spotify"
      className="player-shell fixed inset-x-0 bottom-0 z-30 flex items-center gap-3 border-t border-white/[0.07] px-4 py-3 sm:gap-6 md:px-7"
    >
      <div className="flex min-w-0 flex-1 items-center gap-3 md:w-[30%] md:flex-none">
        {currentTrack?.albumImageUrl ? (
          <img
            src={currentTrack.albumImageUrl}
            alt={`Ảnh bìa ${currentTrack.albumName || currentTrack.name}`}
            className="size-11 shrink-0 rounded-xl object-cover shadow-lg md:size-12"
          />
        ) : (
          <div className="grid size-11 shrink-0 place-items-center rounded-xl border border-white/5 bg-gradient-to-br from-[#3b304c] to-[#22212b] text-lime-300 md:size-12">
            <Music2 size={18} aria-hidden />
          </div>
        )}

        <div className="min-w-0">
          <p className="truncate text-xs font-semibold sm:text-[13px]">
            {currentTrack?.name ??
              (authorized
                ? ready
                  ? "Một giai điệu đang chờ bạn"
                  : "Đang kết nối trình phát…"
                : "Chưa kết nối Spotify")}
          </p>

          <p className="mt-1 truncate text-[10px] text-mist-400 sm:text-[11px]">
            {currentTrack
              ? currentTrack.artists.join(", ")
              : authorized
                ? "Chọn bài hát để phát trên website"
                : "Kết nối tài khoản Spotify Premium để phát nhạc"}
          </p>

          {error && (
            <p
              title={error}
              className="max-w-[220px] truncate text-[10px] text-red-300 sm:max-w-sm"
            >
              {error}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-center gap-2 md:w-[40%]">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={btn}
            disabled={!canControl || !canSkipPrevious}
            onClick={() =>
              void previousTrack().catch(() => undefined)
            }
            aria-label="Bài trước"
          >
            <SkipBack size={17} />
          </button>

          <button
            type="button"
            className="grid size-10 place-items-center rounded-full bg-lime-400 text-ink-950 transition hover:scale-105 hover:bg-lime-300 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!canControl}
            onClick={() =>
              void togglePlayback().catch(() => undefined)
            }
            aria-label={paused ? "Phát nhạc" : "Tạm dừng"}
          >
            {paused ? <Play size={17} fill="currentColor" className="ml-0.5" /> : <Pause size={17} fill="currentColor" />}
          </button>

          <button
            type="button"
            className={btn}
            disabled={!canControl || !canSkipNext}
            onClick={() =>
              void nextTrack().catch(() => undefined)
            }
            aria-label="Bài tiếp theo"
          >
            <SkipForward size={17} />
          </button>
        </div>

        <div className="hidden w-full max-w-md items-center gap-3 text-[9px] text-mist-400 md:flex">
          <span className="tabular-nums">
            {formatTime(displayedPosition)}
          </span>

          <input
            type="range"
            aria-label="Tua bài hát"
            min={0}
            max={maxPosition}
            step={1000}
            value={displayedPosition}
            disabled={!canControl || maxPosition <= 1}
            onChange={(event) => {
              setSeekPreview(Number(event.currentTarget.value));
            }}
            onPointerUp={(event) => {
              commitSeek(Number(event.currentTarget.value));
            }}
            onKeyUp={(event) => {
              commitSeek(Number(event.currentTarget.value));
            }}
            className="h-1 min-w-0 flex-1 cursor-pointer accent-lime-400 disabled:cursor-not-allowed disabled:opacity-40"
          />

          <span className="tabular-nums">
            {formatTime(duration || currentTrack?.durationMs || 0)}
          </span>
        </div>
      </div>

      <PlaybackQueue />
      <div className="hidden min-w-0 flex-1 items-center justify-end gap-4 md:flex">
        {!authorized ? (
          <button
            type="button"
            disabled={!configured}
            onClick={() =>
              connectSpotify(
                window.location.pathname + window.location.search
              )
            }
            className="whitespace-nowrap rounded-full bg-lime-400 px-3 py-2 text-xs font-semibold text-ink-950 hover:bg-lime-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Kết nối Spotify
          </button>
        ) : (
          <label
            className="hidden items-center gap-2 text-mist-300 md:flex"
            aria-label="Âm lượng"
          >
            <Volume2 size={16} />

            <input
              aria-label="Âm lượng Spotify"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={volume}
              onChange={(event) =>
                setVolume(Number(event.target.value))
              }
              className="h-1 w-24 accent-lime-400"
            />
          </label>
        )}
      </div>
    </div>
  );
}
