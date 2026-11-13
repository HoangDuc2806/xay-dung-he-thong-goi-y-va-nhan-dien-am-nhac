"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Compass, Heart, LoaderCircle, Music2, RefreshCw, Save, Search, ThumbsDown } from "lucide-react";
import { AuthGate } from "@/components/auth-gate";
import { PageHeader } from "@/components/page-header";
import { CatalogTrack, getRecommendations, getSimilarTracks, giveFeedback, MusicPreferences, savePreferences, type FeedbackAction } from "@/lib/recommendation-api";

const GENRES=["pop","rock","classic rock","synth-pop","r&b","hip-hop","indie","jazz","funk","progressive rock","electronic","ballad","v-pop","k-pop"];
const MOODS=["chill","happy","sad","romantic","energetic","party","focus","relax"];
const LANGUAGES=["vi","en","ko","ja","other"];

const chip=(active:boolean)=>"rounded-full border px-3 py-1.5 text-xs transition " +(active?"bg-lime-400 text-ink-950 border-lime-400":"bg-ink-950 text-mist-300 border-ink-700 hover:border-lime-500");
function DiscoverContent(){
  const [data,setData]=useState<Awaited<ReturnType<typeof getRecommendations>>|null>(null);
  const [prefs,setPrefs]=useState<MusicPreferences>({genres:[],moods:[],languages:[],artists:[],blocked_artists:[],discovery_level:50});
  const [busy,setBusy]=useState(true);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState("");
  const [selected,setSelected]=useState<string|null>(null);
  const [similar,setSimilar]=useState<CatalogTrack[]>([]);
  const [feedbackPending,setFeedbackPending]=useState<string|null>(null);
  async function refresh(){setBusy(true);setError("");try{const next=await getRecommendations();setData(next);setPrefs(next.preferences);}catch(e){setError(e instanceof Error?e.message:"Không tải được gợi ý.");}finally{setBusy(false);}}
  useEffect(()=>{void refresh();},[]);
  function toggle(field:"genres"|"moods"|"languages",value:string){
    setPrefs(x=>({...x,[field]:x[field].includes(value)?x[field].filter(v=>v!==value):[...x[field],value]}));
  }
  async function save(){setSaving(true);setError("");try{await savePreferences(prefs);await refresh();}catch(e){setError(e instanceof Error?e.message:"Không lưu được sở thích.");}finally{setSaving(false);}}
  async function feedback(track:CatalogTrack,action:FeedbackAction){
    setFeedbackPending(track.id);setError("");
    try{await giveFeedback(track.id,action);await refresh();}
    catch(e){setError(e instanceof Error?e.message:"Không lưu được phản hồi.");}
    finally{setFeedbackPending(null);}
  }
  async function selectSimilar(id:string){
    if(selected===id){setSelected(null);setSimilar([]);return;}
    setSelected(id);setSimilar([]);setError("");
    try{const result=await getSimilarTracks(id);setSimilar(result.items);}
    catch(e){setError(e instanceof Error?e.message:"Không tìm được bài tương tự.");}
  }
  const items=data?.items??[];
  return <div className="space-y-6">
    <section className="rounded-2xl border border-ink-700 bg-ink-900 p-5">
      <h2 className="text-xl font-bold">Sở thích của bạn</h2>
      <p className="mt-2 text-sm text-mist-300">Gợi ý được tạo từ metadata độc lập và các lựa chọn bạn cung cấp; không phân tích lịch sử Spotify.</p>
      {([
        ["Thể loại","genres",GENRES],
        ["Tâm trạng","moods",MOODS],
        ["Ngôn ngữ","languages",LANGUAGES],
      ] as const).map(([heading,field,options])=><div key={field} className="mt-4">
        <h3 className="mb-2 text-sm font-semibold">{heading}</h3>
        <div className="flex flex-wrap gap-2">{options.map(v=><button type="button" key={v} aria-pressed={prefs[field].includes(v)} onClick={()=>toggle(field,v)} className={chip(prefs[field].includes(v))}>{v}</button>)}</div>
      </div>)}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <label className="text-sm font-semibold">Nghệ sĩ yêu thích (ngăn cách bằng dấu phẩy)
          <input type="text" value={prefs.artists.join(", ")} onChange={e=>setPrefs(x=>({...x,artists:e.target.value.split(",")}))}
            placeholder="Ví dụ: Queen, Taylor Swift" className="mt-2 w-full rounded-lg border border-ink-700 bg-ink-950 p-2 text-sm font-normal"/>
        </label>
        <label className="text-sm font-semibold">Nghệ sĩ không muốn gợi ý
          <input type="text" value={prefs.blocked_artists.join(", ")} onChange={e=>setPrefs(x=>({...x,blocked_artists:e.target.value.split(",")}))}
            placeholder="Nhập tên nghệ sĩ" className="mt-2 w-full rounded-lg border border-ink-700 bg-ink-950 p-2 text-sm font-normal"/>
        </label>
      </div>
      <label className="mt-4 block text-sm font-semibold">Mức độ khám phá nhạc mới: {prefs.discovery_level}%
        <input type="range" min="0" max="100" step="10" value={prefs.discovery_level}
          onChange={e=>setPrefs(x=>({...x,discovery_level:Number(e.target.value)}))}
          className="mt-2 block w-full accent-lime-400" aria-label="Mức độ khám phá nhạc mới"/>
      </label>
      <button type="button" onClick={()=>void save()} disabled={saving||busy} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-ink-950 disabled:opacity-50">
        {saving?<LoaderCircle size={16} className="animate-spin"/>:<Save size={16}/>}Lưu sở thích và gợi ý lại
      </button>
    </section>

    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h2 className="text-xl font-bold">Dành riêng cho bạn</h2><p className="mt-1 text-xs text-mist-400">Sắp xếp theo thể loại, tâm trạng và lựa chọn độc lập</p></div>
        <button type="button" aria-label="Tải lại gợi ý" onClick={()=>void refresh()} disabled={busy} className="rounded-lg border border-ink-700 p-2"><RefreshCw size={17}/></button>
      </div>
      {error&&<p role="alert" className="rounded-lg border border-red-700 bg-red-950/30 p-4 text-sm text-red-200">{error}</p>}
      {busy&&<div className="flex items-center gap-2 rounded-xl border border-ink-700 p-5 text-mist-300"><LoaderCircle size={20} className="animate-spin"/>Đang tải gợi ý...</div>}
      {!busy&&!error&&items.length===0&&<div className="rounded-xl border border-dashed border-ink-700 p-7 text-center"><Compass size={26} className="mx-auto mb-2 text-lime-400"/><h3 className="font-semibold">Catalog chưa có dữ liệu</h3><p className="mt-2 text-sm text-mist-300">Hãy chạy migration và seed SQL trong thư mục supabase/seeds. Không có bài hát giả được tạo để lấp chỗ trống.</p></div>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map(track=><article key={track.id} className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
        <div className="flex gap-3">{track.artwork_url?<img src={track.artwork_url} alt="" className="size-16 shrink-0 rounded-lg object-cover"/>:<span className="grid size-16 shrink-0 place-items-center rounded-lg bg-ink-800"><Music2 size={22} className="text-lime-400"/></span>}
          <div className="min-w-0 flex-1"><h3 className="truncate font-semibold">{track.title}</h3><p className="truncate text-sm text-mist-300">{track.artist}</p><p className="truncate text-xs text-mist-400">{track.album||"Bài hát"}</p></div></div>
        <div className="mt-3 flex flex-wrap gap-1">{[...track.genres,...track.moods].slice(0,5).map(x=><span key={x} className="rounded-full bg-ink-800 px-2 py-1 text-[11px]">{x}</span>)}</div>
        <p className="mt-3 text-xs text-mist-300">{track.reasons.join(" · ")} {track.score>0?`· ${Math.round(track.score*100)}% phù hợp`:""}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Link href={`/search?q=${encodeURIComponent(track.spotify_search_query||`${track.title} ${track.artist}`)}`} className="inline-flex items-center gap-1 rounded-lg bg-lime-400 px-3 py-2 text-xs font-semibold text-ink-950"><Search size={13}/>Tìm Spotify</Link>
          <button aria-label={`Thích ${track.title}`} disabled={feedbackPending!==null} onClick={()=>void feedback(track,"like")} className="rounded-lg border border-ink-700 p-2 hover:border-lime-500"><Heart size={16}/></button>
          <button aria-label={`Không thích ${track.title}`} disabled={feedbackPending!==null} onClick={()=>void feedback(track,"dislike")} className="rounded-lg border border-ink-700 p-2 hover:border-red-500"><ThumbsDown size={16}/></button>
          <button disabled={feedbackPending!==null} onClick={()=>void feedback(track,"save")} className="rounded-lg border border-ink-700 px-2 py-2 text-xs">Lưu</button>
          <button disabled={feedbackPending!==null} onClick={()=>void feedback(track,"skip")} className="rounded-lg border border-ink-700 px-2 py-2 text-xs">Bỏ qua</button>
          <button onClick={()=>void selectSimilar(track.id)} className="rounded-lg border border-ink-700 px-2 py-2 text-xs">Tương tự</button>
        </div>
        <p className="mt-2 truncate text-[10px] text-mist-400" title={track.source_url}>Metadata: {track.source}</p>
      </article>)}</div>
    </section>
    {selected&&<section className="rounded-2xl border border-ink-700 bg-ink-900 p-5"><h2 className="mb-3 text-lg font-semibold">Bài hát tương tự</h2>
      {!similar.length?<p className="text-sm text-mist-300">Chưa có bài tương tự trong catalog độc lập.</p>:<ul className="space-y-2">{similar.map(item=><li key={item.id} className="flex items-center justify-between gap-2 border-b border-ink-700 py-2"><span className="min-w-0 truncate text-sm">{item.title} – {item.artist}</span><Link href={`/search?q=${encodeURIComponent(item.spotify_search_query)}`} className="shrink-0 text-xs text-lime-400">Tìm Spotify</Link></li>)}</ul>}
    </section>}
    <p className="text-xs text-mist-400">{data?.message}</p>
  </div>;
}
export default function Page(){return <><PageHeader title="Khám phá" description="Gợi ý âm nhạc từ sở thích và catalog độc lập."/><AuthGate><DiscoverContent/></AuthGate></>}
