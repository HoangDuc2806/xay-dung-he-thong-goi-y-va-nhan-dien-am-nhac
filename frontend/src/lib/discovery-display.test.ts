import { describe, expect, it } from "vitest";
import { emptyPreferences, emptyRecommendationMessage, preferenceSearchQuery } from "./discovery-display";
import type { RecommendationsResponse } from "./recommendation-api";

const response: RecommendationsResponse = {
  source: "independent_catalog", preferences: emptyPreferences(), items: [], message: "",
  status: "no_matches", catalog_size: 15,
};

describe("recommendation states", () => {
  it("does not call an existing catalog empty when no preferences match", () => {
    const value = emptyRecommendationMessage(response);
    expect(value.title).toContain("Chưa có bài phù hợp");
    expect(value.description).toContain("15 bài");
  });
  it("only reports an empty catalog for the explicit empty state", () => {
    expect(emptyRecommendationMessage({ ...response, status: "empty_catalog", catalog_size: 0 }).title).toBe("Kho gợi ý chưa có bài hát");
  });
  it("provides a direct Spotify search for a missing artist or selected mood/language", () => {
    expect(preferenceSearchQuery({ ...emptyPreferences(), artists: ["bray"] })).toBe("bray");
    const query = preferenceSearchQuery({ ...emptyPreferences(), moods: ["sad"], languages: ["vi"] });
    expect(query).toContain("nhạc buồn");
    expect(query).toContain("Việt Nam");
  });
});
