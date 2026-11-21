"use client";

import { Music2, Search, Unplug, AudioLines } from "lucide-react";
import { UserMenu } from "@/components/user-menu";
import { useSpotifyPlayer } from "@/components/spotify-player-provider";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export function TopBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const { configured: spotifyConfigured, authorized: spotifyAuthorized, ready: spotifyReady, connectSpotify, disconnectSpotify } = useSpotifyPlayer();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (term) router.push(`/search?q=${encodeURIComponent(term)}`);
  }

  return (
    <header className="sticky top-0 z-10 border-b border-white/[0.04] bg-ink-950/80 px-4 py-4 backdrop-blur-xl md:px-9 md:py-5">
      <div className="flex items-center gap-3"><AudioLines size={22} className="shrink-0 text-lime-400 md:hidden" aria-hidden /><form onSubmit={onSubmit} role="search" className="relative min-w-0 max-w-xl flex-1">
        <label htmlFor="global-search" className="sr-only">
          Tìm bài hát, nghệ sĩ hoặc album
        </label>
        <Search size={17} aria-hidden className="absolute left-4 top-1/2 -translate-y-1/2 text-mist-400" />
        <input
          id="global-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Tìm bài hát, nghệ sĩ hoặc album"
          className="w-full rounded-full border border-white/[0.05] bg-[#1c1c23] py-3 pl-11 pr-4 text-[13px] outline-none transition placeholder:text-mist-400 focus:border-lime-500/60 focus:bg-ink-800"
        />
      </form><div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">{spotifyAuthorized ? <button type="button" onClick={disconnectSpotify} aria-label="Ngắt kết nối Spotify" title="Ngắt kết nối Spotify" className="inline-flex h-10 items-center gap-2 rounded-full border border-emerald-300/15 bg-emerald-300/[0.04] px-3 text-[11px] font-medium text-emerald-300 hover:bg-emerald-300/10"><span className="size-1.5 rounded-full bg-emerald-300"/><span className="hidden lg:inline">{spotifyReady ? "Spotify đã kết nối" : "Đang kết nối…"}</span><Unplug size={13}/></button> : <button type="button" disabled={!spotifyConfigured} onClick={() => connectSpotify(window.location.pathname + window.location.search)} title={spotifyConfigured ? "Kết nối tài khoản Spotify Premium" : "Cần cấu hình NEXT_PUBLIC_SPOTIFY_CLIENT_ID"} className="inline-flex h-10 items-center gap-2 rounded-full bg-lime-400 px-3 text-xs font-semibold text-ink-950 hover:bg-lime-300 disabled:cursor-not-allowed disabled:opacity-50"><Music2 size={14}/><span className="hidden sm:inline">Kết nối Spotify</span></button>}<UserMenu /></div></div>
    </header>
  );
}
