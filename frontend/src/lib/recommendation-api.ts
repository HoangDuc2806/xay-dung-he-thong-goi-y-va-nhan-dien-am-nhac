import { ApiError, API_URL } from "@/lib/api";
import { requireSupabase } from "@/lib/supabase";

export type MusicPreferences = {
  genres: string[]; moods: string[]; languages: string[];
  artists: string[]; blocked_artists: string[]; discovery_level: number;
};
export type CatalogTrack = {
  id: string; title: string; artist: string; album: string | null;
  release_year: number | null; genres: string[]; moods: string[]; tags: string[];
  language: string; artwork_url: string | null;
  spotify_search_query: string; source: string; source_url: string;
  source_license: string; score: number; reasons: string[];
};
export type RecommendationsResponse = {
  source: "independent_catalog"; preferences: MusicPreferences;
  items: CatalogTrack[]; message: string;
};
export type FeedbackAction = "like" | "dislike" | "save" | "skip";

async function request<T>(path: string, method="GET", body?: unknown): Promise<T> {
  const { data, error } = await requireSupabase().auth.getSession();
  if (error || !data.session?.access_token) throw new ApiError("Hãy đăng nhập lại.", 401);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method, cache: "no-store",
      headers: { Authorization: `Bearer ${data.session.access_token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Không kết nối được tới hệ thống gợi ý.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as {detail?:string;error?:{message?:string}}|null;
    throw new ApiError(payload?.error?.message || payload?.detail || "Không tải được gợi ý.", response.status);
  }
  return response.json() as Promise<T>;
}
export const getRecommendations=()=>request<RecommendationsResponse>("/api/recommendations");
export const savePreferences=(prefs:MusicPreferences)=>request<MusicPreferences>("/api/recommendations/preferences","PUT",prefs);
export const giveFeedback=(trackId:string,action:FeedbackAction)=>request<{track_id:string;action:FeedbackAction}>("/api/recommendations/feedback","POST",{track_id:trackId,action});
export const getSimilarTracks=(id:string)=>request<{items:CatalogTrack[]}>("/api/recommendations/similar/"+encodeURIComponent(id));
