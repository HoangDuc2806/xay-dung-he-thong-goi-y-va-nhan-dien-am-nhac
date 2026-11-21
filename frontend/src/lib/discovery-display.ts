import type { MusicPreferences, RecommendationsResponse } from "./recommendation-api";

export const GENRES = ["pop", "rock", "classic rock", "synth-pop", "r&b", "hip-hop", "indie", "jazz", "funk", "progressive rock", "electronic", "ballad", "v-pop", "k-pop"];
export const MOODS = ["chill", "happy", "sad", "romantic", "energetic", "party", "focus", "relax"];
export const LANGUAGES = ["vi", "en", "ko", "ja", "other"];
const LABELS: Record<string, string> = {
  vi: "Tiếng Việt", en: "Tiếng Anh", ko: "Tiếng Hàn", ja: "Tiếng Nhật", other: "Khác",
  chill: "Chill", happy: "Vui vẻ", sad: "Buồn", romantic: "Lãng mạn",
  energetic: "Năng lượng", party: "Tiệc tùng", focus: "Tập trung", relax: "Thư giãn",
};
export const preferenceLabel = (value: string) => LABELS[value] ?? value;
export const emptyPreferences = (): MusicPreferences => ({ genres: [], moods: [], languages: [], artists: [], blocked_artists: [], discovery_level: 50 });

export function emptyRecommendationMessage(data: RecommendationsResponse): { title: string; description: string } {
  if (data.status === "empty_catalog" || data.catalog_size === 0) {
    return { title: "Kho gợi ý chưa có bài hát", description: "Bạn vẫn có thể tìm và nghe nhạc trên Spotify trong lúc kho gợi ý được bổ sung." };
  }
  return {
    title: "Chưa có bài phù hợp với lựa chọn của bạn",
    description: `Kho gợi ý${data.catalog_size ? ` hiện có ${data.catalog_size} bài` : ""}, nhưng chưa có kết quả phù hợp sau khi áp dụng sở thích và phản hồi. Bạn có thể xem các bài hiện có hoặc tìm trực tiếp trên Spotify.`,
  };
}

export function preferenceSearchQuery(prefs: MusicPreferences): string {
  if (prefs.artists.length) return prefs.artists.join(" ");
  const moods: Record<string, string> = { sad: "nhạc buồn", happy: "nhạc vui", chill: "chill", romantic: "nhạc tình", energetic: "sôi động", focus: "tập trung", relax: "thư giãn", party: "party" };
  const parts = [...prefs.moods.map(value => moods[value] ?? value), ...prefs.genres];
  if (prefs.languages.includes("vi")) parts.push("Việt Nam");
  else if (prefs.languages.includes("en")) parts.push("English");
  return parts.join(" ") || "nhạc Việt";
}
