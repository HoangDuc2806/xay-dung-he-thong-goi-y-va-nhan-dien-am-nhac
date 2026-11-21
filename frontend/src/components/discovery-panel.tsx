"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, Compass, ExternalLink, Heart, LoaderCircle, Music2, RefreshCw, Save, Search, SlidersHorizontal, ThumbsDown, X } from "lucide-react";
import { getRecommendations, getSimilarTracks, giveFeedback, savePreferences, searchRecommendationMetadata, type CatalogTrack, type FeedbackAction, type MusicPreferences, type RecommendationsResponse } from "@/lib/recommendation-api";
import { emptyPreferences, emptyRecommendationMessage, GENRES, LANGUAGES, MOODS, preferenceLabel, preferenceSearchQuery } from "@/lib/discovery-display";

const button = "inline-flex items-center justify-center gap-2 rounded-xl border border-ink-600 px-4 py-2.5 text-sm font-medium transition hover:border-lime-500 disabled:cursor-not-allowed disabled:opacity-50";
const primary = `${button} border-transparent bg-lime-400 text-ink-950 hover:bg-lime-300`;
const input = "mt-2 w-full rounded-xl border border-ink-600 bg-ink-950 px-3 py-3 text-sm font-normal outline-none focus:border-lime-400";
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Không kết nối được hệ thống gợi ý.";
const splitArtists = (text: string) => [...new Set(text.split(",").map(value => value.trim()).filter(Boolean))];

export function DiscoveryPanel() {
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [prefs, setPrefs] = useState<MusicPreferences>(emptyPreferences);
  const [artistText, setArtistText] = useState("");
  const [blockedText, setBlockedText] = useState("");
  const [editing, setEditing] = useState(true);
  const [browse, setBrowse] = useState(false);
  const method = "hybrid" as const;
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [feedbackPending, setFeedbackPending] = useState<string | null>(null);
  const [metadataTitle, setMetadataTitle] = useState("");
  const [metadataArtist, setMetadataArtist] = useState("");
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [metadataMessage, setMetadataMessage] = useState("");
  const [metadataTracks, setMetadataTracks] = useState<CatalogTrack[]>([]);
  const [selected, setSelected] = useState<CatalogTrack | null>(null);
  const [similar, setSimilar] = useState<CatalogTrack[]>([]);
  const [similarBusy, setSimilarBusy] = useState(false);
  const [similarError, setSimilarError] = useState("");
  const requestId = useRef(0);
  const similarId = useRef(0);

  function applyPreferences(value: MusicPreferences) {
    setPrefs(value);
    setArtistText(value.artists.join(", "));
    setBlockedText(value.blocked_artists.join(", "));
  }

  async function load(replacePreferences = false, catalogView = browse, likedTrackId?: string) {
    const id = ++requestId.current;
    setBusy(true); setLoadError("");
    try {
      const result = await getRecommendations(catalogView, method, likedTrackId);
      if (id !== requestId.current) return null;
      setData(result);
      if (replacePreferences) applyPreferences(result.preferences);
      return result;
    } catch (error) {
      if (id !== requestId.current) return null;
      throw error;
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  }

  useEffect(() => {
    void load(true, false).then(result => {
      if (result) setEditing(![...result.preferences.genres, ...result.preferences.moods, ...result.preferences.languages, ...result.preferences.artists, ...result.preferences.blocked_artists].length);
    }).catch(error => { if (requestId.current) setLoadError(errorMessage(error)); });
    return () => { requestId.current++; similarId.current++; };
    // Initialize once; subsequent user actions explicitly refresh saved results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle(field: "genres" | "moods" | "languages", value: string) {
    setNotice("");
    setPrefs(previous => ({ ...previous, [field]: previous[field].includes(value) ? previous[field].filter(item => item !== value) : [...previous[field], value] }));
  }

  async function save(useLearnedTaste = false) {
    setSaving(true); setFormError(""); setNotice("");
    let saved = false;
    try {
      const artists = useLearnedTaste ? [] : splitArtists(artistText);
      const blocked = splitArtists(blockedText);
      if (artists.length > 12 || blocked.length > 12) throw new Error("Mỗi danh sách nghệ sĩ chỉ được tối đa 12 tên.");
      const value = await savePreferences({ ...prefs, ...(useLearnedTaste ? { genres: [], moods: [], languages: [] } : {}), artists, blocked_artists: blocked });
      saved = true;
      applyPreferences(value);
      setData(previous => previous ? { ...previous, preferences: value, items: [], status: undefined } : previous);
      setBrowse(false); setEditing(false); setNotice("Đã lưu sở thích và cập nhật lựa chọn của bạn.");
      await load(false, false);
    } catch (error) {
      if (saved) setLoadError(`Sở thích đã lưu, nhưng chưa tải lại được kết quả. ${errorMessage(error)}`);
      else setFormError(errorMessage(error));
    } finally { setSaving(false); }
  }

  async function refresh(catalogView = browse) {
    setBrowse(catalogView);
    try { await load(false, catalogView); }
    catch (error) { setLoadError(errorMessage(error)); }
  }

  async function feedback(track: CatalogTrack, action: FeedbackAction) {
    setFeedbackPending(track.id); setLoadError("");
    try {
      await giveFeedback(track.id, action);
      setMetadataTracks(previous => previous.map(item => item.id === track.id ? { ...item, feedback_action: action } : item));
      setNotice(action === "like" ? "Đã ghi nhận bài bạn thích để cải thiện gợi ý." : action === "skip" ? "Đã bỏ qua bài này trong gợi ý." : "Đã ghi nhận. Bài này sẽ được loại khỏi gợi ý.");
      if (action === "like") {
        setBrowse(false);
        const updated = await load(false, false, track.id);
        if (updated?.new_candidates) setNotice(`Đã tìm thêm ${updated.new_candidates} bài. ${updated.new_in_top_10 ?? 0} bài mới vào 10 gợi ý đầu.`);
        else if (updated?.metadata_lookup?.some(entry => entry.status === "unavailable")) {
          setNotice("Đã ghi nhận bài bạn thích. MusicBrainz đang bận, gợi ý đã được cập nhật từ các bài hiện có.");
        }
      } else await load(false);
    } catch (error) { setLoadError(errorMessage(error)); }
    finally { setFeedbackPending(null); }
  }

  async function findTrack() {
    if (!metadataTitle.trim() || !metadataArtist.trim() || metadataBusy) return;
    setMetadataBusy(true);
    setMetadataMessage("");
    setMetadataTracks([]);
    try {
      const result = await searchRecommendationMetadata(metadataTitle.trim(), metadataArtist.trim());
      setMetadataTracks(result.items);
      if (!result.items.length) {
        setMetadataMessage(result.status === "unavailable" ? "MusicBrainz đang bận. Hãy thử lại sau." : "Chưa tìm thấy bản ghi khớp cả tên bài và nghệ sĩ.");
      }
    } catch (error) {
      setMetadataMessage(errorMessage(error));
    } finally {
      setMetadataBusy(false);
    }
  }

  async function showSimilar(track: CatalogTrack) {
    const id = ++similarId.current;
    if (selected?.id === track.id) { setSelected(null); setSimilar([]); setSimilarBusy(false); return; }
    setSelected(track); setSimilar([]); setSimilarError(""); setSimilarBusy(true);
    try {
      const result = await getSimilarTracks(track.id,method);
      if (id === similarId.current) setSimilar(result.items);
    } catch (error) { if (id === similarId.current) setSimilarError(errorMessage(error)); }
    finally { if (id === similarId.current) setSimilarBusy(false); }
  }

  const items = data?.items ?? [];
  const status = data?.status ?? (items.some(item => item.score > 0) ? "personalized" : "discovery");
  const savedPrefs = data?.preferences ?? prefs;
  const summary = [...savedPrefs.genres, ...savedPrefs.moods.map(preferenceLabel), ...savedPrefs.languages.map(preferenceLabel), ...savedPrefs.artists];
  const missingArtists = data?.missing_artists ?? [];
  const metadataLookups = data?.metadata_lookup ?? [];
  const metadataUnavailable = metadataLookups.some(entry => entry.status === "unavailable");
  const metadataAmbiguous = metadataLookups.some(entry => entry.status === "ambiguous");
  const empty = data ? emptyRecommendationMessage(data) : null;
  const allBusy = saving || busy || feedbackPending !== null;
  const rankingDescription = browse ? "Các bài hiện có trong kho gợi ý." : {
    item_knn: "Dựa trên những bài bạn thích và người nghe có gu tương tự.",
    content_based: "Dựa trên thông tin nghệ sĩ, album và các bài bạn thích.",
    hybrid: "Kết hợp gu người nghe và thông tin của những bài bạn thích.",
    popularity: "Thích vài bài để bắt đầu cá nhân hóa. Hiện đang gợi ý các bài phổ biến.",
    metadata: "Dựa trên sở thích và phản hồi đã lưu của bạn.",
    catalog: "Các bài hiện có trong kho gợi ý.",
  }[data?.model?.algorithm ?? "metadata"];

  return <div className="space-y-6">
    <section id="music-preferences" className="surface scroll-mt-28 p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-lime-400/10 text-lime-300"><SlidersHorizontal size={20} /></span>
          <div><h2 className="text-lg font-semibold">Gu âm nhạc của bạn</h2><p className="mt-1 text-sm text-mist-300">Chọn điều bạn thích để tìm bài phù hợp trong catalog gợi ý.</p></div>
        </div>
        <button type="button" className={`${button} shrink-0 !px-3`} aria-label={editing ? "Thu gọn sở thích" : "Chỉnh sửa sở thích"} aria-expanded={editing} aria-controls="preference-form" onClick={() => setEditing(!editing)}><span className="hidden sm:inline">{editing ? "Thu gọn" : "Chỉnh sửa"}</span><ChevronDown size={16} className={editing ? "rotate-180" : ""} /></button>
      </div>
      {!editing && <div className="mt-4 flex flex-wrap gap-2">{summary.length ? summary.slice(0, 12).map((value, index) => <span key={`${value}-${index}`} className="rounded-full border border-lime-400/15 bg-lime-400/[0.06] px-3 py-1.5 text-xs text-lime-300">{value}</span>) : <p className="text-sm text-mist-400">Chưa có sở thích. Mở Chỉnh sửa để bắt đầu.</p>}</div>}
      {editing && <form id="preference-form" onSubmit={event => { event.preventDefault(); void save(); }} className="mt-6">
        <fieldset disabled={saving || busy} className="grid gap-6 disabled:opacity-60 xl:grid-cols-[1.3fr_1fr]">
          <div className="space-y-5">{([
            ["Thể loại", "genres", GENRES], ["Tâm trạng", "moods", MOODS], ["Ngôn ngữ", "languages", LANGUAGES],
          ] as const).map(([label, field, options]) => <div key={field}><h3 className="mb-2.5 text-sm font-semibold">{label}</h3><div className="flex flex-wrap gap-2">{options.map(value => <button type="button" key={value} aria-pressed={prefs[field].includes(value)} onClick={() => toggle(field, value)} className={`rounded-full border px-3 py-2 text-xs transition ${prefs[field].includes(value) ? "border-lime-400 bg-lime-400 font-semibold text-ink-950" : "border-ink-600 bg-ink-950 text-mist-200 hover:border-lime-500"}`}>{preferenceLabel(value)}</button>)}</div></div>)}</div>
          <div className="space-y-5 xl:border-l xl:border-ink-700 xl:pl-6">
            <label className="block text-sm font-semibold">Nghệ sĩ yêu thích<input value={artistText} onChange={event => { setArtistText(event.target.value); setNotice(""); }} className={input} placeholder="Ví dụ: B-Ray, Queen" /><span className="mt-2 block text-xs font-normal text-mist-400">Tối đa 12 tên, ngăn cách bằng dấu phẩy. Web sẽ tra MusicBrainz nếu kho chưa có nghệ sĩ.</span></label>
            <label className="block text-sm font-semibold">Nghệ sĩ không muốn gợi ý<input value={blockedText} onChange={event => { setBlockedText(event.target.value); setNotice(""); }} className={input} placeholder="Nhập tên nghệ sĩ cần ẩn" /><span className="mt-2 block text-xs font-normal text-mist-400">Tối đa 12 tên. Những nghệ sĩ này được loại khỏi danh sách.</span></label>
            <label className="block text-sm font-semibold">Độ đa dạng nghệ sĩ <span className="float-right text-lime-300">{prefs.discovery_level}%</span><input type="range" min="0" max="100" step="10" value={prefs.discovery_level} onChange={event => { setPrefs(previous => ({ ...previous, discovery_level: Number(event.target.value) })); setNotice(""); }} className="mt-4 block w-full" /><span className="mt-2 block text-xs font-normal leading-relaxed text-mist-400">Cao: ưu tiên ít bài hơn từ mỗi nghệ sĩ. Điều này không bổ sung bài mới vào catalog.</span></label>
          </div>
        </fieldset>
        {formError && <p role="alert" className="mt-4 text-sm text-red-300">{formError}</p>}
        <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-ink-700 pt-5"><button type="submit" className={primary} disabled={saving || busy}>{saving ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}Lưu và cập nhật gợi ý</button><button type="button" disabled={saving || busy} className={button} onClick={() => { applyPreferences(emptyPreferences()); setNotice(""); }}>Đặt lại lựa chọn</button></div>
      </form>}
    </section>

    <details className="surface px-5 py-4">
      <summary className="cursor-pointer text-sm font-semibold">Tìm bài để thêm vào gu của bạn</summary>
      <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void findTrack(); }}>
        <label className="min-w-40 flex-1 text-sm">Tên bài hát<input className={input} value={metadataTitle} maxLength={120} required onChange={event => setMetadataTitle(event.target.value)} /></label>
        <label className="min-w-40 flex-1 text-sm">Nghệ sĩ<input className={input} value={metadataArtist} maxLength={80} required onChange={event => setMetadataArtist(event.target.value)} /></label>
        <button type="submit" className={button} disabled={metadataBusy || allBusy}><Search size={16} />{metadataBusy ? "Đang tìm…" : "Tìm bài"}</button>
      </form>
      {metadataMessage && <p className="mt-3 text-sm text-mist-300" role="status">{metadataMessage}</p>}
      {metadataTracks.length > 0 && <ul className="mt-3 divide-y divide-ink-700">
        {metadataTracks.map(track => {
          const liked = track.feedback_action === "like" || track.feedback_action === "save";
          return <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={track.id}>
            <div className="min-w-0"><p className="text-sm font-medium">{track.title}</p><p className="text-xs text-mist-400">{track.artist}{track.album ? ` · ${track.album}` : ""}</p></div>
            <button type="button" className={`${button} text-xs`} disabled={allBusy || metadataBusy || liked} onClick={() => void feedback(track, "like")}><Heart size={15} fill={liked ? "currentColor" : "none"} />{liked ? "Đã thích" : "Thích để gợi ý"}</button>
          </li>;
        })}
      </ul>}
    </details>

    {notice && <p role="status" className="flex items-start gap-2 rounded-xl border border-lime-400/15 bg-lime-400/[0.05] px-4 py-3 text-sm text-lime-300"><Check size={17} className="mt-0.5 shrink-0" />{notice}</p>}

    <section className="space-y-4" aria-label="Kết quả gợi ý">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-1"><h2 className="text-xl font-semibold">{status === "discovery" ? "Khám phá dành cho bạn" : "Gợi ý cho bạn"}</h2><p className="mt-1 max-w-xl text-sm text-mist-400">{rankingDescription}</p></div>
        <div className="flex w-full items-end gap-2 sm:w-auto">
          <button type="button" className={`${button} !px-3`} aria-label="Tải lại gợi ý" disabled={allBusy} onClick={() => void refresh()}><RefreshCw size={17} className={busy ? "animate-spin" : ""} /></button>
        </div>
      </div>
      {!busy && !browse && !items.length && (savedPrefs.genres.length+savedPrefs.moods.length+savedPrefs.languages.length)>0 && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-600 px-4 py-3 text-sm text-mist-300"><span>Chưa có bài phù hợp với các lựa chọn hiện tại.</span><button type="button" disabled={allBusy} className="shrink-0 font-medium text-lime-300 disabled:opacity-50" onClick={() => void save(true)}>Mở rộng lựa chọn</button></div>}

      {browse && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-600 p-4 text-sm text-mist-300"><span>Bạn đang xem catalog. Sở thích đã lưu vẫn được giữ lại.</span><button type="button" disabled={allBusy} className="font-semibold text-lime-300" onClick={() => void refresh(false)}>Quay lại gợi ý cá nhân</button></div>}
      {!busy && !browse && missingArtists.length > 0 && <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-4"><p className="text-sm text-amber-200">Chưa có bài cho <strong>{missingArtists.join(", ")}</strong>.</p><p className="mt-2 text-sm text-mist-300">{metadataUnavailable ? "MusicBrainz đang bận. Bạn có thể thử tải lại gợi ý sau." : metadataAmbiguous ? "Có nghệ sĩ trùng tên. Hãy thử tìm bằng tên bài ở trên." : "Bạn có thể thử tìm bằng tên bài ở trên hoặc mở Spotify."}</p><div className="mt-3 flex flex-wrap gap-2">{missingArtists.map(name => <Link key={name} href={`/search?q=${encodeURIComponent(name)}`} className={`${button} !py-2`}><Search size={14} />Tìm {name}</Link>)}</div></div>}
      {loadError && <div role="alert" className="rounded-xl border border-red-700 bg-red-950/20 p-4 text-sm text-red-200">{loadError}<button type="button" className="ml-3 underline" onClick={() => void refresh()}>Thử lại</button></div>}
      {busy && <div role="status" className="flex items-center gap-3 rounded-2xl border border-ink-700 p-6 text-sm text-mist-300"><LoaderCircle size={20} className="animate-spin" />Đang tìm bài phù hợp…</div>}

      {!busy && !loadError && data && items.length === 0 && empty && <div className="rounded-2xl border border-dashed border-ink-600 bg-ink-900/40 p-6 text-center sm:p-9"><span className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-lime-400/10 text-lime-300"><Compass size={26} /></span><h3 className="text-lg font-semibold">{empty.title}</h3><p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-mist-300">{empty.description}</p>
        {!!data.available_languages?.length && <p className="mt-3 text-sm text-mist-400">Ngôn ngữ hiện có: {data.available_languages.map(preferenceLabel).join(", ")}.{!data.available_moods?.includes("sad") && savedPrefs.moods.includes("sad") ? " Chưa có bài gắn tâm trạng Buồn." : ""}</p>}
        <div className="mt-5 flex flex-wrap justify-center gap-3">{data.catalog_size !== 0 && !browse && <button type="button" className={primary} onClick={() => void refresh(true)}>Xem các bài hiện có</button>}<Link href={`/search?q=${encodeURIComponent(preferenceSearchQuery(savedPrefs))}`} className={button}><Search size={16} />Tìm trên Spotify</Link><button type="button" className={button} onClick={() => { setEditing(true); document.getElementById("music-preferences")?.scrollIntoView({ behavior: "smooth" }); }}>Chỉnh sở thích</button></div>
      </div>}

      {!busy && <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{items.map(track => <article key={track.id} className="rounded-2xl border border-ink-700 bg-ink-900 p-5 transition hover:border-lime-500/30">
        <div className="flex items-start gap-3">{track.artwork_url ? <img src={track.artwork_url} alt="" className="size-16 shrink-0 rounded-xl object-cover" /> : <span className="grid size-16 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[#3b304c] to-ink-800 text-lime-300"><Music2 size={26} strokeWidth={1.5} /></span>}<div className="min-w-0 flex-1"><h3 className="truncate font-semibold" title={track.title}>{track.title}</h3><p className="mt-1 truncate text-sm text-mist-300">{track.artist}</p><p className="mt-1 truncate text-xs text-mist-400">{track.album || "Bài hát"}</p></div></div>
        <div className="mt-4 flex flex-wrap gap-1.5">{[...new Set([...track.genres, ...track.moods])].slice(0, 5).map(value => <span key={value} className="rounded-full border border-white/5 bg-ink-800 px-2.5 py-1 text-xs text-mist-200">{preferenceLabel(value)}</span>)}</div>
        <p className="mt-4 text-sm leading-relaxed text-mist-300">{track.reasons.join(" · ")}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-ink-700 pt-4"><Link href={`/search?q=${encodeURIComponent(track.spotify_search_query || `${track.title} ${track.artist}`)}`} className={`${primary} !px-3 !py-2 text-xs`}><Search size={14} />Tìm Spotify</Link><button type="button" title="Thích bài này" aria-label={`Thích ${track.title}`} aria-pressed={track.feedback_action === "like" || track.feedback_action === "save"} disabled={allBusy} onClick={() => void feedback(track, "like")} className={`${button} !p-2.5 ${track.feedback_action === "like" || track.feedback_action === "save" ? "text-lime-300" : ""}`}><Heart size={16} fill={track.feedback_action === "like" || track.feedback_action === "save" ? "currentColor" : "none"} /></button><button type="button" title="Không thích bài này" aria-label={`Không thích ${track.title}`} disabled={allBusy} onClick={() => void feedback(track, "dislike")} className={`${button} !p-2.5`}><ThumbsDown size={16} /></button><button type="button" disabled={allBusy} onClick={() => void feedback(track, "skip")} className={`${button} !px-3 !py-2 text-xs`}>Bỏ qua</button><button type="button" onClick={() => void showSimilar(track)} className={`${button} !px-3 !py-2 text-xs`}>Tương tự</button></div>
        <p className="mt-3 text-xs text-mist-400">Nguồn: {track.source_url?.startsWith("https://") ? <a href={track.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-lime-300">{track.source}<ExternalLink size={11} /></a> : track.source}</p>
      </article>)}</div>}
    </section>

    {selected && <section className="surface p-5 sm:p-6"><div className="mb-4 flex items-center justify-between gap-4"><h2 className="text-lg font-semibold">Tương tự “{selected.title}”</h2><button type="button" aria-label="Đóng bài tương tự" className="rounded-lg p-2 hover:bg-ink-800" onClick={() => { similarId.current++; setSelected(null); }}><X size={18} /></button></div>{similarBusy ? <p role="status" className="flex items-center gap-2 text-sm text-mist-300"><LoaderCircle size={18} className="animate-spin" />Đang tìm bài tương tự…</p> : similarError ? <p role="alert" className="text-sm text-red-300">{similarError}</p> : similar.length ? <ul className="divide-y divide-ink-700">{similar.map(track => <li key={track.id} className="flex items-center justify-between gap-4 py-3"><p className="min-w-0 truncate text-sm">{track.title}<span className="ml-2 text-mist-400">{track.artist}</span></p><Link href={`/search?q=${encodeURIComponent(track.spotify_search_query || `${track.title} ${track.artist}`)}`} className="shrink-0 text-sm text-lime-300">Tìm Spotify</Link></li>)}</ul> : <p className="text-sm text-mist-300">Chưa có bài tương tự trong catalog hiện tại.</p>}</section>}
    <p className="text-xs leading-relaxed text-mist-400">Thích hoặc bỏ qua các bài để điều chỉnh gợi ý theo gu của bạn. Spotify dùng để tìm và phát bài.</p>
  </div>;
}
