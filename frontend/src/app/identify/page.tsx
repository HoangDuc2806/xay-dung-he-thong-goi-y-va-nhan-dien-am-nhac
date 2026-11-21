"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AudioLines,
  CheckCircle2,
  ExternalLink,
  FileAudio,
  LoaderCircle,
  Mic,
  RotateCcw,
  Search,
  Square,
  Headphones,
} from "lucide-react";
import { AuthGate } from "@/components/auth-gate";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { useAuth } from "@/components/providers";
import { identifyAudio, fetchSpotifyNowPlaying, listRecognitionHistory, getRecognitionStatus, type RecognitionStatus, type MusicRecognitionResponse, type SpotifyNowPlayingResponse } from "@/lib/api";
import { getValidSpotifyAccessToken } from "@/lib/spotify-oauth";
import { useSpotifyPlayer } from "@/components/spotify-player-provider";
import { requireSupabase } from "@/lib/supabase";
import { recordingToWav } from "@/lib/recording-wav";
import { summarizeMicrophone, type MicrophoneTrial } from "@/lib/microphone-evaluation";
import { compareLocalRecognition, listLocalRecognitionCatalog, type LocalComparisonResponse, type LocalRecognitionTrack } from "@/lib/api";

const panel = "rounded-2xl border border-ink-700 bg-ink-900 p-5 sm:p-6";
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const RECORDING_LIMIT_SECONDS = 15;

function formatBytes(bytes: number) {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds: number) {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function IdentifyContent() {
  const { user } = useAuth();
  const { authorized, connectSpotify } = useSpotifyPlayer();
  const [nowPlaying, setNowPlaying] = useState<SpotifyNowPlayingResponse | null>(null);
  const [nowPlayingBusy, setNowPlayingBusy] = useState(false);
  const [nowPlayingError, setNowPlayingError] = useState("");
  const [history, setHistory] = useState<Array<{ id: string; status: string; duration_seconds: number; results: MusicRecognitionResponse["results"]; created_at: string }>>([]);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<MusicRecognitionResponse | null>(null);
  const [recognitionStatus, setRecognitionStatus] = useState<RecognitionStatus | null>(null);
  const [method,setMethod]=useState<"configured"|"landmark"|"mfcc_dtw"|"compare">("configured");
  const [comparison, setComparison] = useState<(LocalComparisonResponse & { totalMs: number; scored: boolean }) | null>(null);
  const [expectedTrack, setExpectedTrack] = useState("");
  const [trialLabel, setTrialLabel] = useState("");
  const [trials, setTrials] = useState<MicrophoneTrial[]>([]);
  const mounted = useRef(true);
  const [localCatalog,setLocalCatalog]=useState<LocalRecognitionTrack[]>([]);
  const [statusError, setStatusError] = useState("");
  const startingRef = useRef(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const intervalRef = useRef<number | null>(null);
  const autoStopRef = useRef<number | null>(null);

  useEffect(() => {
    if (!file) { setPreviewUrl(""); return; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function clearRecordingTimers() {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    if (autoStopRef.current !== null) window.clearTimeout(autoStopRef.current);
    intervalRef.current = null;
    autoStopRef.current = null;
  }

  function stopMicrophoneTracks() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearRecordingTimers();
      const recorder = recorderRef.current;
      if (recorder) recorder.onstop = null;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      stopMicrophoneTracks();
    };
    // The refs are stable; this effect is only for unmount cleanup.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function acceptFile(nextFile: File | null) {
    setError("");
    setResult(null);
    setComparison(null);
    setExpectedTrack("");
    if (nextFile && nextFile.size > MAX_FILE_BYTES) {
      setFile(null);
      setError("Tệp quá lớn. Vui lòng chọn tệp không vượt quá 20 MB.");
      return;
    }
    setFile(nextFile);
  }

  async function startRecording(mode: "microphone" | "tab" = "microphone") {
    if (startingRef.current || recording || busy) return;
    startingRef.current = true;
    setError("");
    setResult(null);
    setFile(null);
    setComparison(null);

    if (typeof navigator === "undefined" || !navigator.mediaDevices ||
        (mode === "tab" ? !navigator.mediaDevices.getDisplayMedia : !navigator.mediaDevices.getUserMedia)) {
      setError("Trình duyệt không hỗ trợ nguồn âm thanh này. Hãy dùng micro hoặc tải tệp.");
      startingRef.current = false;
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      setError("Trình duyệt chưa hỗ trợ MediaRecorder. Hãy cập nhật trình duyệt hoặc tải tệp âm thanh lên.");
      startingRef.current = false;
      return;
    }

    setBusy(true);
    try {
      const stream = mode === "microphone"
        ? await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
          })
        : await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
      if (!mounted.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      if (stream.getAudioTracks().length === 0) {
        stream.getTracks().forEach(track => track.stop());
        setError("Nguồn chia sẻ không có audio track. Hãy bật chia sẻ âm thanh tab nếu trình duyệt hỗ trợ.");
        return;
      }
      streamRef.current = stream;
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find(
        (candidate) => MediaRecorder.isTypeSupported(candidate),
      );
      const audioStream = new MediaStream(stream.getAudioTracks());
      const recorder = mimeType ? new MediaRecorder(audioStream, { mimeType }) : new MediaRecorder(audioStream);
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        recorder.onstop = null;
        setError("Không thể ghi âm. Hãy thử lại hoặc tải tệp âm thanh lên.");
        setRecording(false);
        clearRecordingTimers();
        stopMicrophoneTracks();
      };
      recorder.onstop = async () => {
        clearRecordingTimers();
        stopMicrophoneTracks();
        setRecording(false);
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (blob.size === 0) {
          setError("Không thu được âm thanh. Hãy cấp quyền micro và thử lại.");
          return;
        }
        setBusy(true);
        try {
          const captured = await recordingToWav(blob);
          if (!mounted.current) return;
          acceptFile(captured);
          if (mode === "microphone") await runIdentification(captured, trialLabel);
        } catch {
          const extension = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
          acceptFile(new File([blob], `ghi-am-${Date.now()}.${extension}`, { type: blob.type }));
          setError("Trình duyệt chưa chuyển được bản ghi sang WAV. Có thể thử gửi bản ghi gốc nếu máy chủ đã cài FFmpeg, hoặc dùng Chrome/Edge mới và ghi lại.");
        } finally { setBusy(false); }
      };

      recorder.start(250);
      startedAtRef.current = Date.now();
      setRecordingSeconds(0);
      setRecording(true);
      intervalRef.current = window.setInterval(() => {
        setRecordingSeconds(Math.min(RECORDING_LIMIT_SECONDS, Math.floor((Date.now() - startedAtRef.current) / 1000)));
      }, 250);
      autoStopRef.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, RECORDING_LIMIT_SECONDS * 1000);
    } catch (caught) {
      stopMicrophoneTracks();
      const message = caught instanceof Error && caught.name === "NotAllowedError"
        ? "Bạn chưa cấp quyền sử dụng micro. Hãy cho phép micro trong trình duyệt rồi thử lại."
        : "Không mở được micro. Kiểm tra thiết bị và quyền truy cập micro của trình duyệt.";
      setError(message);
    } finally {
      startingRef.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  function stopRecording() {
    clearRecordingTimers();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }

  async function runIdentification(input = file, microphoneLabel = "") {
    if (!input || !user) return;
    const started = performance.now();
    setError("");
    setResult(null);
    setComparison(null);
    setBusy(true);
    try {
      const { data, error: sessionError } = await requireSupabase().auth.getSession();
      if (sessionError) throw sessionError;
      if (!data.session?.access_token) throw new Error("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.");
      if (!mounted.current) return;
      if (method === "compare") {
        const measured = await compareLocalRecognition(input, data.session.access_token);
        if (!mounted.current) return;
        if (microphoneLabel) {
          setTrials(previous => [...previous, { ...measured, expected: microphoneLabel === "outside" ? null : microphoneLabel }]);
          setTrialLabel("");
        }
        setExpectedTrack(microphoneLabel);
        setComparison({ ...measured, totalMs: Math.round(performance.now() - started), scored: Boolean(microphoneLabel) });
        return;
      }
      const response = await identifyAudio(input, data.session.access_token, undefined, method);
      setResult(response);
      if(method==="configured") void listRecognitionHistory(data.session.access_token).then(setHistory).catch(() => undefined);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể nhận diện âm thanh lúc này.");
    } finally {
      setBusy(false);
    }
  }

  async function checkNowPlaying() {
    setNowPlayingBusy(true);setNowPlayingError("");
    try {
      const session = await requireSupabase().auth.getSession();
      const userToken=session.data.session?.access_token;
      const spotifyToken=await getValidSpotifyAccessToken();
      if(!userToken) throw new Error("Hãy đăng nhập vào Music Discovery.");
      if(!spotifyToken) throw new Error("Hãy kết nối lại tài khoản Spotify.");
      setNowPlaying(await fetchSpotifyNowPlaying(userToken,spotifyToken));
    } catch(e) {
      setNowPlayingError(e instanceof Error?e.message:"Không lấy được trạng thái Spotify.");
    } finally {setNowPlayingBusy(false);}
  }

  useEffect(()=>{
    if(!user)return;
    let alive=true;
    void requireSupabase().auth.getSession().then(async ({data})=>{
      if(data.session?.access_token){
        void listLocalRecognitionCatalog(data.session.access_token).then(value=>{if(alive)setLocalCatalog(value.items);}).catch(()=>undefined);
        void getRecognitionStatus(data.session.access_token).then(value=>{
          if(alive){setRecognitionStatus(value);setStatusError("");}
        }).catch(()=>{if(alive)setStatusError("Chưa kiểm tra được trạng thái nhận diện. Hãy tải lại trang.");});
        const rows=await listRecognitionHistory(data.session.access_token);
        if(alive)setHistory(rows);
      }
    }).catch(()=>undefined);
    return ()=>{alive=false;};
  },[user?.id]);

  function reset() {
    setFile(null);
    setResult(null);
    setComparison(null);
    setExpectedTrack("");
    setError("");
    setRecordingSeconds(0);
    const input = document.getElementById("audio-file") as HTMLInputElement | null;
    if (input) input.value = "";
  }

  function downloadTrials() {
    const report = { recordings: trials, summary: [
      summarizeMicrophone(trials, "landmark"), summarizeMicrophone(trials, "mfcc_dtw"),
    ] };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `ket-qua-micro-${Date.now()}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <div className="space-y-5">
      <section className={panel} aria-label="Trạng thái nhận diện">
        <h2 className="font-semibold">Chọn phương pháp nhận diện</h2>
        <label className="mt-3 block text-sm">Nguồn nhận diện<select disabled={busy||recording} value={method} onChange={event=>{setMethod(event.target.value as typeof method);setResult(null);setComparison(null);setError("");}} className="mt-2 block w-full rounded-xl border border-ink-600 bg-ink-950 px-3 py-3 sm:max-w-lg"><option value="configured">Dịch vụ đang cấu hình trên máy chủ (AudD / AcoustID)</option><option value="compare">So sánh Landmark và MFCC + DTW</option><option value="landmark">Thử nghiệm nội bộ — Landmark kiểu Shazam</option><option value="mfcc_dtw">Thử nghiệm nội bộ — MFCC + DTW</option></select></label>
        <p className="mt-2 text-sm text-mist-300">Để micro gần nguồn đang phát nhạc như loa, điện thoại, TV hoặc radio và ghi đoạn rõ 10–15 giây. Kết quả phụ thuộc chất lượng bản ghi và kho của nguồn nhận diện.</p>
        {statusError && <p role="status" className="mt-2 text-sm text-amber-300">{statusError}</p>}
        {method!=="configured" && <div className="mt-4 rounded-xl border border-lime-400/20 bg-lime-400/[0.04] p-4 text-sm"><p>Phát một đoạn trong khoảng đã lập chỉ mục bên dưới, rồi ghi âm hoặc tải WAV 5–15 giây.</p>{recognitionStatus && !recognitionStatus.local_comparison_ready && <p className="mt-2 text-amber-300">Máy chủ chưa có đủ bộ tham chiếu và báo cáo hiệu chỉnh.</p>}<ul className="mt-3 grid gap-2 sm:grid-cols-2">{localCatalog.map(track=><li key={track.id}><a className="text-lime-300 underline" href={track.source_url} target="_blank" rel="noreferrer">{track.title}</a><span className="ml-2 text-xs text-mist-400">{track.artist} · {track.license} · {Math.floor(track.duration_seconds)} giây đầu</span></li>)}</ul></div>}
        {recognitionStatus && method==="configured" && <div className="mt-3 space-y-2 text-sm">
          {recognitionStatus.mode !== "audd" && (!recognitionStatus.tools.ffmpeg || !recognitionStatus.tools.ffprobe) && <p role="alert" className="text-amber-300">Máy chủ còn thiếu FFmpeg hoặc FFprobe. Nhận diện chưa sẵn sàng xử lý bản ghi âm.</p>}
          {(recognitionStatus.mode === "hybrid" || recognitionStatus.mode === "landmark") && !recognitionStatus.catalog_available && <p role="alert" className="text-amber-300">Chưa kết nối được kho fingerprint nội bộ. Cần hoàn tất thiết lập database.</p>}
          {recognitionStatus.mode === "audd" && <p className={recognitionStatus.audd_configured ? "text-lime-300" : "text-amber-300"}>{recognitionStatus.audd_configured ? "Đang chọn AudD để nhận diện bản ghi micro; không cần tự nạp kho nhạc. Token cần còn hiệu lực và hạn mức." : "Chưa có token AudD trên máy chủ. Cần thêm AUDD_API_TOKEN vào backend/.env.local rồi khởi động lại backend."}</p>}
          {recognitionStatus.mode === "landmark" && <p className="text-mist-300">Đang dùng thuật toán fingerprint nội bộ.</p>}
          {recognitionStatus.mode === "acoustid" && (!recognitionStatus.acoustid_configured || !recognitionStatus.tools.fpcalc) && <p role="alert" className="text-amber-300">Máy chủ chưa có đủ cấu hình AcoustID hoặc công cụ tạo fingerprint.</p>}
        </div>}
        {method === "compare" && <div className="mt-4 space-y-3 text-sm">
          <label className="block">Bài sắp phát qua loa
            <select disabled={busy || recording} value={trialLabel} onChange={event => setTrialLabel(event.target.value)}
              className="mt-1 block w-full rounded-xl border border-ink-600 bg-ink-950 p-3 sm:max-w-lg">
              <option value="">Thử tự do</option>
              <option value="outside">Bản thu ngoài kho</option>
              {localCatalog.map(track => <option key={track.id} value={track.id}>{track.title} — {track.artist}</option>)}
            </select>
          </label>
          <p className="text-mist-300">Chọn đáp án trước khi bấm nghe để tính một lượt đo qua micro cho cả hai thuật toán.</p>
          {trials.length > 0 && <div className="space-y-2 rounded-xl border border-ink-700 p-3">
            <p className="font-semibold">Kết quả phiên đo · {trials.length} đoạn micro đã có đáp án</p>
            {(["landmark", "mfcc_dtw"] as const).map(name => {
              const s = summarizeMicrophone(trials, name);
              return <p key={name}><strong>{name === "landmark" ? "Landmark" : "MFCC + DTW"}</strong>
                {" · "}Đúng {s.correct}/{s.total} ({Math.round(1000 * s.correct / s.total) / 10}%)
                {s.known > 0 && ` · Nhận đúng trong kho ${s.correctKnown}/${s.known}`}
                {s.unknown > 0 && ` · Nhận nhầm ngoài kho ${s.falseAccepts}/${s.unknown}`}
                {` · Xử lý trung bình ${s.meanProcessingMs} ms`}</p>;
            })}
            <button type="button" onClick={downloadTrials} className="rounded-lg border border-ink-600 px-3 py-2">Tải kết quả phiên đo (.json)</button>
            <p className="text-xs text-mist-400">Tải kết quả trước khi rời trang để giữ số liệu của phiên này.</p>
          </div>}
        </div>}
      </section>
      <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <section className={panel} aria-labelledby="record-title">
          <h2 id="record-title" className="flex items-center gap-2 text-xl font-bold">
            <Mic size={21} className="text-lime-400" /> Thu âm hoặc tải tệp
          </h2>
          <p className="mb-5 mt-2 text-sm leading-relaxed text-mist-300">
            Để micro gần nguồn nhạc và ghi một đoạn rõ khoảng 10–15 giây. Bạn cũng có thể tải lên một tệp âm thanh có sẵn.
          </p>

          <div className="rounded-2xl border border-ink-700 bg-ink-950 p-5 text-center">
            <div className={`mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full ${recording ? "bg-red-500/15 text-red-300" : "bg-lime-400/10 text-lime-400"}`}>
              {recording ? <AudioLines size={30} className="animate-pulse" /> : <Mic size={30} />}
            </div>
            <p className="text-2xl font-semibold tabular-nums">{formatDuration(recordingSeconds)}</p>
            <p className="mb-4 mt-1 text-xs text-mist-300">
              {recording ? `Đang ghi âm · tự dừng sau ${RECORDING_LIMIT_SECONDS} giây` : "Bấm để bật micro. Sau tối đa 15 giây, web tự gửi đoạn thu để nhận diện."}
            </p>
            {recording ? (
              <button type="button" onClick={stopRecording} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-500 px-5 py-3 text-sm font-semibold text-white hover:bg-red-400">
                <Square size={16} /> Dừng ghi âm
              </button>
            ) : (
              <button type="button" onClick={() => void startRecording()} disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-xl bg-lime-400 px-5 py-3 text-sm font-semibold text-ink-950 hover:bg-lime-300 disabled:opacity-50">
                <Mic size={16} /> Nghe và nhận diện
              </button>
            )}
          </div>

          <button type="button" onClick={() => void startRecording("tab")} disabled={busy||recording}
            className="mt-3 w-full rounded-xl border border-ink-600 px-4 py-2 text-sm text-mist-100 hover:border-lime-500 disabled:opacity-50">
            Thu âm tab/màn hình có quyền sử dụng (nếu trình duyệt hỗ trợ)
          </button>
          <p className="mt-2 text-xs text-mist-400">Chỉ chia sẻ âm thanh bạn được phép xử lý. Không dùng chức năng này để trích xuất hoặc phân tích luồng âm thanh Spotify.</p>
          <div className="my-5 flex items-center gap-3 text-xs uppercase tracking-widest text-mist-400">
            <span className="h-px flex-1 bg-ink-700" /> hoặc tải lên <span className="h-px flex-1 bg-ink-700" />
          </div>

          <label htmlFor="audio-file" className="flex cursor-pointer flex-col items-center rounded-2xl border border-dashed border-ink-600 bg-ink-950/60 p-5 text-center transition hover:border-lime-500">
            <FileAudio size={25} className="mb-2 text-lime-400" />
            <span className="text-sm font-semibold">Chọn tệp âm thanh</span>
            <span className="mt-1 text-xs text-mist-300">MP3, WAV, WebM/Opus, M4A, FLAC, OGG, WMA, AIFF, CAF... · tối đa 20 MB</span>
            <input
              id="audio-file"
              type="file"
              accept="audio/*,.mp3,.wav,.flac,.ogg,.oga,.m4a,.mp4,.aac,.webm,.opus,.wma,.aif,.aiff,.caf,.mka,.3gp,.amr"
              className="sr-only"
              disabled={busy || recording}
              onChange={(event) => acceptFile(event.target.files?.[0] ?? null)}
            />
          </label>

          {file && (
            <div className="mt-4 flex items-center gap-3 rounded-xl border border-ink-700 bg-ink-950 p-3">
              <FileAudio size={20} className="shrink-0 text-lime-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-mist-300">{formatBytes(file.size)}</p>
              </div>
              <button type="button" onClick={reset} disabled={busy} className="rounded-lg px-2 py-1 text-xs text-mist-300 hover:bg-ink-800">Bỏ tệp</button>
            </div>
          )}
          {previewUrl && <div className="mt-3"><p className="mb-2 text-xs text-mist-300">Nghe lại để kiểm tra micro có thu rõ nhạc từ nguồn phát.</p><audio controls src={previewUrl} className="w-full" preload="metadata" /></div>}

          <button
            type="button"
            onClick={() => void runIdentification()}
            disabled={!file || busy || recording}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-lime-400 px-4 py-3 font-semibold text-ink-950 transition hover:bg-lime-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? <LoaderCircle size={18} className="animate-spin" /> : <Search size={18} />}
            {busy ? "Đang xử lý âm thanh…" : method === "compare" ? "So sánh hai thuật toán" : "Nhận diện bài hát"}
          </button>
          <p className="mt-3 text-xs leading-relaxed text-mist-400">{method==="configured" && recognitionStatus?.mode === "audd" ? "Đoạn thu qua micro được tự động gửi tới AudD để tìm bài hát. Website chỉ lưu thông tin kết quả." : "Âm thanh được xử lý tạm thời trên backend và không được lưu thành tệp trong thư viện."}</p>
        </section>

        <section className={panel} aria-labelledby="results-title" aria-live="polite">
          <h2 id="results-title" className="flex items-center gap-2 text-xl font-bold">
            <AudioLines size={21} className="text-lime-400" /> Kết quả nhận diện
          </h2>
          <p className="mb-5 mt-2 text-sm text-mist-300">Nguồn nhận diện được ghi rõ ở từng kết quả. Điểm khớp, nếu có, không phải xác suất chắc chắn.</p>

          {error && (
            <div role="alert" className="flex gap-3 rounded-xl border border-red-800/70 bg-red-950/30 p-4 text-sm text-red-200">
              <AlertCircle size={19} className="mt-0.5 shrink-0" /> <p>{error}</p>
            </div>
          )}

          {!error && !result && !comparison && (
            <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-ink-700 p-6 text-center">
              <div className="mb-3 rounded-2xl bg-ink-800 p-4 text-mist-300"><Search size={27} /></div>
              <p className="font-semibold">Chưa có kết quả</p>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-mist-300">Bấm “Nghe và nhận diện” để dùng micro hoặc chọn một tệp âm thanh rồi gửi.</p>
            </div>
          )}

          {comparison && (
            <div className="space-y-3">
              <p className="text-sm text-mist-300">Cùng bản ghi {comparison.duration_seconds} giây · hoàn tất sau {comparison.totalMs} ms</p>
              <label className="block text-sm">Bài đã phát để đối chiếu
                <select disabled={comparison.scored} value={expectedTrack} onChange={event => setExpectedTrack(event.target.value)} className="mt-1 block w-full rounded-xl border border-ink-600 bg-ink-950 p-3">
                  <option value="">Chọn nhãn nếu muốn kiểm tra đúng sai</option>
                  <option value="outside">Bài ngoài kho</option>
                  {localCatalog.map(track => <option value={track.id} key={track.id}>{track.title} — {track.artist}</option>)}
                </select>
              </label>
              <ul className="space-y-2">
                {comparison.results.map(row => {
                  const correct = row.track_id === (expectedTrack === "outside" ? null : expectedTrack);
                  return <li key={row.method} className="rounded-xl border border-ink-700 p-3">
                    <p className="font-semibold">{row.method === "landmark" ? "Landmark" : "MFCC + DTW"}</p>
                    <p className="mt-1 text-sm text-mist-300">{row.track ? `${row.track.title} — ${row.track.artists.join(", ")}` : "Chưa tìm thấy bài phù hợp"}</p>
                    <p className="mt-1 text-xs text-mist-400">{row.elapsed_ms} ms xử lý{expectedTrack ? ` · ${correct ? "Đúng" : "Sai"}` : ""}</p>
                  </li>;
                })}
              </ul>
            </div>
          )}

          {result && result.status === "not_found" && (
            <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-ink-700 p-6 text-center">
              <AlertCircle size={28} className="mb-3 text-amber-300" />
              <p className="font-semibold">Chưa tìm thấy bài hát</p>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-mist-300">{result.message}</p>
              <p className="mt-2 text-xs text-mist-400">Đoạn đã phân tích: {result.duration_seconds} giây</p>
            </div>
          )}
          {result?.warnings?.map((warning, index) => <p key={index} role="status" className="my-3 rounded-lg border border-amber-700 p-3 text-sm text-amber-200">{warning}</p>)}

          {result && result.status === "matched" && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 rounded-xl border border-lime-600/30 bg-lime-400/5 p-4">
                <CheckCircle2 size={21} className="mt-0.5 shrink-0 text-lime-400" />
                <div>
                  <p className="font-semibold text-lime-300">Đã tìm thấy kết quả phù hợp</p>
                  <p className="mt-1 text-sm text-mist-300">{result.message}</p>
                </div>
              </div>
              {result.results.map((track, index) => (
                <article key={track.musicbrainz_recording_id ?? track.acoustid_id ?? `${track.title}-${index}`} className="rounded-xl border border-ink-700 bg-ink-950 p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-ink-800 text-lime-400"><AudioLines size={23} /></div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-semibold leading-snug">{track.title}</h3>
                      <p className="mt-1 text-sm text-mist-300">{track.artists.length ? track.artists.join(", ") : "Chưa có thông tin nghệ sĩ"}</p>
                      <p className="mt-1 text-xs text-mist-400">Nguồn: {track.recognition_method === "audd" ? "AudD (dịch vụ nhận diện)" : track.recognition_method === "mfcc_dtw" ? "MFCC + DTW (thuật toán nội bộ)" : track.recognition_method === "mdvn_landmark" ? "MDVN Landmark (thuật toán nội bộ)" : "Chromaprint + AcoustID"}</p>
                      {(track.album || track.year) && <p className="mt-1 text-xs text-mist-400">{[track.album, track.year].filter(Boolean).join(" · ")}</p>}
                    </div>
                    {track.score !== null && <span className="shrink-0 rounded-full bg-ink-800 px-2.5 py-1 text-xs tabular-nums text-lime-300">{Math.round(track.score * 100)}% điểm</span>}
                  </div>
                  {track.score !== null && <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-ink-800">
                    <div className="h-full rounded-full bg-lime-400" style={{ width: `${Math.round(track.score * 100)}%` }} />
                  </div>}
                  <div className="mt-3 flex flex-wrap gap-3 text-xs">
                    {track.spotify_url && <a href={track.spotify_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-lime-500 px-3 py-2 text-lime-300">Mở đúng bài trên Spotify <ExternalLink size={12} /></a>}
                    <Link href={`/search?q=${encodeURIComponent(`${track.title} ${track.artists.join(" ")}`)}`} className="inline-flex items-center gap-1 rounded-lg bg-lime-400 px-3 py-2 font-semibold text-ink-950 hover:bg-lime-300">Tìm bài này trên Spotify <ExternalLink size={12} /></Link>
                    {track.musicbrainz_url && <a href={track.musicbrainz_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-ink-700 px-3 py-2 text-lime-300 hover:underline">MusicBrainz <ExternalLink size={12} /></a>}
                    {track.acoustid_url && <a href={track.acoustid_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-ink-700 px-3 py-2 text-mist-300 hover:text-lime-300 hover:underline">AcoustID <ExternalLink size={12} /></a>}
                  </div>
                </article>
              ))}
              {result.results.some(track => track.recognition_method === "mdvn_landmark" || track.recognition_method === "mfcc_dtw") && <p className="text-xs leading-relaxed text-mist-400">Điểm số không phải xác suất. Hai thuật toán mới được đánh giá trên tập nhạc mở nhỏ với nhiễu tạo bằng máy tính.</p>}
              <button type="button" onClick={reset} className="inline-flex items-center gap-2 rounded-xl border border-ink-700 px-4 py-2 text-sm hover:border-lime-500"><RotateCcw size={15} /> Nhận diện đoạn khác</button>
            </div>
          )}
        </section>
      </div>
      <section className={panel}>
        <h2 className="flex items-center gap-2 text-xl font-bold"><Headphones size={20} className="text-lime-400"/>Spotify Now Playing</h2>
        <p className="mt-2 text-sm text-mist-300">Đọc metadata bài đang phát từ Spotify API, không phải nhận diện dựa trên âm thanh. Cần tài khoản Spotify đã cấp quyền.</p>
        <button type="button" disabled={nowPlayingBusy} onClick={()=>authorized?void checkNowPlaying():connectSpotify("/identify")}
          className="mt-4 inline-flex items-center gap-2 rounded-lg border border-lime-500 px-4 py-2 text-sm text-lime-300 disabled:opacity-50">
          {nowPlayingBusy?<LoaderCircle className="animate-spin" size={16}/>:<Headphones size={16}/>}
          {authorized?"Kiểm tra bài đang phát":"Kết nối Spotify"}
        </button>
        {nowPlayingError&&<p role="alert" className="mt-2 text-sm text-red-300">{nowPlayingError}</p>}
        {nowPlaying?.status==="not_playing"&&<p className="mt-3 text-sm text-mist-300">Spotify không báo có bài hát đang phát.</p>}
        {nowPlaying?.track&&<div className="mt-4 flex items-center gap-3 rounded-xl border border-ink-700 p-3">
          {nowPlaying.track.image_url&&<img src={nowPlaying.track.image_url} alt="" className="size-14 rounded-lg object-cover"/>}
          <div className="min-w-0 flex-1"><p className="truncate font-semibold">{nowPlaying.track.name}</p>
            <p className="truncate text-sm text-mist-300">{nowPlaying.track.artists.join(", ")}</p>
          </div>
          {nowPlaying.track.spotify_url&&<a href={nowPlaying.track.spotify_url} target="_blank" rel="noreferrer" className="text-sm text-lime-400">Spotify</a>}
        </div>}
      </section>
      <section className={panel}>
        <h2 className="text-xl font-bold">Lịch sử nhận diện</h2>
        <p className="mt-2 text-xs text-mist-300">Chỉ lưu metadata kết quả nhận diện; không lưu lại file âm thanh.</p>
        {history.length===0?<p className="mt-3 text-sm text-mist-300">Chưa có lịch sử.</p>:<ul className="mt-3 space-y-2">
          {history.slice(0,15).map(row=><li key={row.id} className="rounded-lg border border-ink-700 p-3 text-sm">
            <span className="font-medium">{row.results[0]?.title??"Chưa nhận diện được"}</span>
            <span className="ml-2 text-xs text-mist-400">{new Date(row.created_at).toLocaleString("vi-VN")}</span>
          </li>)}
        </ul>}
      </section>
    </div>
  );
}

export default function Page() {
  return (
    <>
      <PageHeader title="Nhận diện bài hát" description="Dùng micro hoặc tải tệp âm thanh để tìm tên bài hát, nghệ sĩ và album." />
      <AuthGate><IdentifyContent /></AuthGate>
    </>
  );
}
