import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("./supabase", () => ({ requireSupabase: () => ({ auth: {
  getSession: async () => ({ data: { session: { access_token: "test-session" } }, error: null }),
} }) }));
import { getRecommendations, preferencesPayload, savePreferences } from "./recommendation-api";

const preferences = {
  genres: ["ballad"], moods: ["sad"], languages: ["vi", "en"],
  artists: [], blocked_artists: [], discovery_level: 50,
};
afterEach(() => vi.unstubAllGlobals());

describe("preference save contract", () => {
  it("drops database ownership/timestamp fields from an older backend response", async () => {
    const fromDatabase = { ...preferences, user_id: "owner-id", updated_at: "date" };
    expect(preferencesPayload(fromDatabase)).toEqual(preferences);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(preferences), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await savePreferences(fromDatabase);
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual(preferences);
  });
  it("shows the invalid field when the API returns a validation error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
      message: "Dữ liệu gửi lên không hợp lệ.", details: [{ field: "body.artists", message: "Too many items" }],
    } }), { status: 422 })));
    await expect(savePreferences(preferences)).rejects.toThrow("body.artists");
  });
  it("loads suggestions and browsing without an external listening account", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await getRecommendations(false);
    expect(fetchMock.mock.calls[0]![0]).not.toContain("listenbrainz_user");
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));
    await getRecommendations(true);
    expect(fetchMock.mock.calls[1]![0]).toContain("browse=true");
    expect(fetchMock.mock.calls[1]![0]).not.toContain("listenbrainz_user");
  });
  it("sends the selected recommendation method", async () => {
    const fetchMock=vi.fn().mockResolvedValue(new Response("{}",{status:200}));
    vi.stubGlobal("fetch",fetchMock);
    await getRecommendations(false,"hybrid");
    expect(fetchMock.mock.calls[0]![0]).toContain("method=hybrid");
  });
});
