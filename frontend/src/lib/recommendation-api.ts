import { ApiError, API_URL } from "./api";
import { requireSupabase } from "./supabase";

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
  feedback_action?: FeedbackAction | null;
};
export type RecommendationsResponse = {
  source: "independent_catalog"; preferences: MusicPreferences;
  items: CatalogTrack[]; message: string;
  status?: "empty_catalog" | "no_matches" | "personalized" | "discovery";
  catalog_size?: number;
  available_artists?: string[];
  missing_artists?: string[];
  metadata_lookup?: { artist: string; status: "found" | "not_found" | "ambiguous" | "unavailable"; count: number }[];
  new_candidates?: number;
  new_in_top_10?: number;
  available_genres?: string[];
  available_moods?: string[];
  available_languages?: string[];
  view?: "catalog" | "personalized";
  model?: {
    loaded: boolean; algorithm: "item_knn" | "content_based" | "hybrid" | "popularity" | "metadata" | "catalog";
    requested_method?: RecommendationMethod; available_methods?: RecommendationMethod[];
    trained_users: number; trained_items: number; matched_seeds: number;
    profile_source: "listenbrainz_recent" | "app_feedback";
    recent_listens: number; accepted_listens: number;
  };
};
export type FeedbackAction = "like" | "dislike" | "save" | "skip";
export type RecommendationMethod = "item_knn" | "content_based" | "hybrid";

export function preferencesPayload(prefs: MusicPreferences): MusicPreferences {
  // Explicitly pick editable fields; GET responses from older backends may
  // contain user_id/updated_at, which the strict PUT schema rejects.
  return {
    genres: prefs.genres, moods: prefs.moods, languages: prefs.languages,
    artists: prefs.artists, blocked_artists: prefs.blocked_artists,
    discovery_level: prefs.discovery_level,
  };
}

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
    const payload = await response.json().catch(() => null) as {detail?:string;error?:{message?:string;details?:Array<{field?:string;message?:string}>}}|null;
    const details = payload?.error?.details?.map(value => `${value.field ?? ""}: ${value.message ?? ""}`).join("; ");
    const message = payload?.error?.message || payload?.detail || "Không tải được gợi ý.";
    throw new ApiError(details ? `${message} (${details})` : message, response.status);
  }
  return response.json() as Promise<T>;
}
export function getRecommendations(browse=false, method: RecommendationMethod="hybrid", likedTrackId?: string) {
  const params = new URLSearchParams();
  if (browse) params.set("browse", "true");
  else params.set("expand_metadata", "true");
  if (!browse && likedTrackId) params.set("liked_track_id", likedTrackId);
  params.set("method", method);
  return request<RecommendationsResponse>(`/api/recommendations${params.size ? `?${params}` : ""}`);
}
export const savePreferences=(prefs:MusicPreferences)=>request<MusicPreferences>("/api/recommendations/preferences","PUT",preferencesPayload(prefs));
export const giveFeedback=(trackId:string,action:FeedbackAction)=>request<{track_id:string;action:FeedbackAction}>("/api/recommendations/feedback","POST",{track_id:trackId,action});
export const getSimilarTracks=(id:string,method:RecommendationMethod="item_knn")=>request<{items:CatalogTrack[]}>("/api/recommendations/similar/"+encodeURIComponent(id)+(method==="item_knn"?"":`?method=${method}`));
export const searchRecommendationMetadata = (title: string, artist: string) => request<{
  status: "found" | "not_found" | "unavailable";
  items: CatalogTrack[];
}>("/api/recommendations/metadata/search", "POST", { title, artist });
