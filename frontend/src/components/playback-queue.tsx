"use client";

import { useEffect, useRef, useState } from "react";
import { ListMusic, Music2, RefreshCw, X } from "lucide-react";
import { useSpotifyPlayer } from "./spotify-player-provider";
import { getValidSpotifyAccessToken } from "@/lib/spotify-oauth";

import { readPlaybackQueue, type QueueItem } from "@/lib/playback-queue";

export function PlaybackQueue() {
  const { authorized, currentTrack, queueRevision } = useSpotifyPlayer();
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authorized || !open) return;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const token = await getValidSpotifyAccessToken();
        if (!token) throw new Error("Hãy kết nối lại Spotify.");
        const queued = await readPlaybackQueue(token, controller.signal);
        if (!controller.signal.aborted) setItems(queued);
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Không tải được danh sách chờ.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [authorized, open, currentTrack?.uri, queueRevision, refresh]);

  return <>
    <button type="button" title="Danh sách chờ" aria-label="Danh sách chờ" aria-haspopup="dialog"
      className="rounded-lg p-2 text-mist-300 hover:bg-ink-700 hover:text-lime-300"
      onClick={() => { dialog.current?.showModal(); setOpen(true); }}><ListMusic size={20} /></button>
    <dialog ref={dialog} onClose={() => setOpen(false)} aria-labelledby="queue-title"
      className="queue-drawer rounded-2xl border border-ink-600 bg-ink-900 p-5 text-mist-100 shadow-2xl">
      <div className="flex items-center justify-between gap-4">
        <h2 id="queue-title" className="text-xl font-bold">Danh sách chờ</h2>
        <div className="flex gap-2">
          {authorized && <button aria-label="Tải lại danh sách chờ" disabled={loading} onClick={() => setRefresh(n => n + 1)}><RefreshCw size={17} /></button>}
          <button aria-label="Đóng danh sách chờ" onClick={() => dialog.current?.close()}><X size={20} /></button>
        </div>
      </div>
      {currentTrack && <div className="my-5 rounded-xl bg-ink-800 p-3">
        <p className="mb-2 text-xs font-semibold text-lime-300">Bài hiện tại</p>
        <strong>{currentTrack.name}</strong><p className="text-sm text-mist-300">{currentTrack.artists.join(", ")}</p>
      </div>}
      <h3 className="my-3 font-semibold">Tiếp theo</h3>
      {!authorized ? <p>Kết nối Spotify để xem danh sách chờ.</p>
        : loading ? <p role="status">Đang tải…</p>
        : error ? <p role="alert">{error}</p>
        : !items.length ? <p>Chưa có bài chờ. Phát một bài rồi chọn “Thêm vào danh sách chờ” trên bài bạn muốn nghe tiếp.</p>
        : <ol className="space-y-2">{items.map((item, index) => {
          const image = item.album?.images?.[0]?.url ?? item.images?.[0]?.url;
          return <li key={`${item.uri}-${index}`} className="flex items-center gap-3">
            <span className="w-5 text-right text-xs text-mist-400">{index + 1}</span>
            {image ? <img src={image} alt="" className="size-10 rounded-md" /> : <Music2 size={28} />}
            <div className="min-w-0"><p className="truncate text-sm font-medium">{item.name}</p>
              <p className="truncate text-xs text-mist-300">{item.artists?.map(a => a.name).join(", ") ?? item.show?.name}</p></div>
          </li>;
        })}</ol>}
    </dialog>
  </>;
}
