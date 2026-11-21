export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = { status: string; service: string };

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { signal });
  } catch {
    throw new ApiError("Không kết nối được tới máy chủ.");
  }
  if (!res.ok) throw new ApiError("Máy chủ trả về lỗi.", res.status);
  return (await res.json()) as T;
}

export const getHealth = (signal?: AbortSignal) => apiGet<HealthResponse>("/api/health", signal);


export type RecognizedTrack = {
  title: string;
  artists: string[];
  album: string | null;
  year: number | null;
  score: number | null;
  spotify_url?: string | null;
  acoustid_id: string | null;
  musicbrainz_recording_id: string | null;
  musicbrainz_url: string | null;
  acoustid_url: string | null;
  recognition_method?: "acoustid" | "mdvn_landmark" | "audd" | "mfcc_dtw";
};

export type MusicRecognitionResponse = {
  status: "matched" | "not_found";
  message: string;
  duration_seconds: number;
  results: RecognizedTrack[];
  warnings?: string[];
};

export type RecognitionStatus = {
  local_comparison_ready?: boolean;
  mode: "hybrid" | "landmark" | "acoustid" | "audd";
  algorithm: string;
  tools: { ffmpeg: boolean; ffprobe: boolean; fpcalc: boolean };
  acoustid_configured: boolean;
  audd_configured: boolean;
  catalog_available: boolean;
  message: string;
};

export async function getRecognitionStatus(token: string): Promise<RecognitionStatus> {
  const response = await fetch(`${API_URL}/api/identify/status`, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
  });
  if (!response.ok) throw new ApiError("Không kiểm tra được cấu hình nhận diện.", response.status);
  return response.json();
}

export type LocalRecognitionTrack = {id:string;title:string;artist:string;source_url:string;license:string;license_url:string;duration_seconds:number};
export async function listLocalRecognitionCatalog(token: string): Promise<{items:LocalRecognitionTrack[]}> {
  const response=await fetch(`${API_URL}/api/identify/local-catalog`,{headers:{Authorization:`Bearer ${token}`},cache:"no-store"});
  if(!response.ok) throw new ApiError("Chưa đọc được kho thử nghiệm nội bộ.",response.status);
  return response.json();
}

export type LocalComparisonResponse = {
  duration_seconds: number;
  results: { method: "landmark" | "mfcc_dtw"; track_id: string | null; track: RecognizedTrack | null; elapsed_ms: number }[];
};

async function uploadRecognition<T>(path: string, file: File, accessToken: string, signal?: AbortSignal): Promise<T> {
  const form = new FormData();
  form.append("file", file, file.name);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/identify${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body: form,
      signal,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Không kết nối được tới máy chủ nhận diện.");
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { message?: string }; detail?: string } | null;
    const message = body?.error?.message ?? body?.detail ?? "Không thể nhận diện âm thanh.";
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export function identifyAudio(file: File, accessToken: string, signal?: AbortSignal, method: "configured" | "landmark" | "mfcc_dtw" = "configured") {
  return uploadRecognition<MusicRecognitionResponse>(method === "configured" ? "" : `/local?method=${method}`, file, accessToken, signal);
}

export function compareLocalRecognition(file: File, accessToken: string) {
  return uploadRecognition<LocalComparisonResponse>("/local/compare", file, accessToken);
}


export type SpotifyTrack = {
  id: string;
  name: string;
  artists: string[];
  album_name: string | null;
  album_image_url: string | null;
  release_date: string | null;
  duration_ms: number;
  spotify_url: string;
  uri: string;
};

export type SpotifySearchResponse = {
  provider: "spotify";
  query: string;
  market: string;
  items: SpotifyTrack[];
  limit: number;
  offset: number;
  next_offset: number | null;
  total: number | null;
};

export async function searchSpotifyTracks(query: string, signal?: AbortSignal, offset=0): Promise<SpotifySearchResponse> {
  const params = new URLSearchParams({ q: query, limit: "10", market: "VN", offset: String(offset) });
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/spotify/search?${params.toString()}`, {
      signal,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Không kết nối được máy chủ tìm kiếm Spotify.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { message?: string }; detail?: string } | null;
    throw new ApiError(body?.error?.message ?? body?.detail ?? "Không tìm kiếm được trên Spotify.", response.status);
  }
  return (await response.json()) as SpotifySearchResponse;
}


export type SpotifyNowPlayingResponse = {
  status: "playing"|"paused"|"not_playing";
  track: null | {id:string|null; name:string; artists:string[]; album:string|null; image_url:string|null; spotify_url:string|null; duration_ms:number|null};
};
export async function fetchSpotifyNowPlaying(supabaseToken:string, spotifyToken:string):Promise<SpotifyNowPlayingResponse>{
  const response=await fetch(`${API_URL}/api/spotify/now-playing`,{
    headers:{"Authorization":`Bearer ${supabaseToken}`,"X-Spotify-Access-Token":spotifyToken},cache:"no-store",
  });
  if(!response.ok){
    const value=await response.json().catch(()=>null) as {error?:{message?:string}}|null;
    throw new ApiError(value?.error?.message||"Không lấy được bài đang phát trên Spotify.",response.status);
  }
  return response.json() as Promise<SpotifyNowPlayingResponse>;
}
export async function listRecognitionHistory(token:string):Promise<Array<{id:string;status:string;duration_seconds:number;results:RecognizedTrack[];created_at:string}>>{
  const response=await fetch(`${API_URL}/api/identify/history`,{headers:{Authorization:`Bearer ${token}`},cache:"no-store"});
  if(!response.ok)throw new ApiError("Không tải được lịch sử nhận diện.",response.status);
  return response.json();
}
