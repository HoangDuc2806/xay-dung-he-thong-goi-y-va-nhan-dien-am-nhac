import { beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("./api", () => ({ searchSpotifyTracks: vi.fn() }));
import { searchSpotifyTracks, type SpotifySearchResponse, type SpotifyTrack } from "./api";
import { loadSpotifyBatch, mergeSpotifyTracks, playbackUris } from "./spotify-pages";

function track(id: number): SpotifyTrack {
  return { id: String(id), name: `Track ${id}`, artists: [], album_name: null,
    album_image_url: null, release_date: null, duration_ms: 10000,
    spotify_url: `https://open.spotify.com/track/${id}`, uri: `spotify:track:${id}` };
}
function page(offset: number, next: number | null): SpotifySearchResponse {
  return { provider: "spotify", query: "pop", market: "VN", limit: 10, offset,
    total: 100, next_offset: next, items: Array.from({ length: 10 }, (_, i) => track(offset + i)) };
}
beforeEach(() => vi.mocked(searchSpotifyTracks).mockReset());

describe("Spotify playback queue", () => {
  const list = [track(1), track(2), track(3)];
  it("starts at the chosen track and queues the remaining visible rows in order", () => {
    expect(playbackUris(track(2), list)).toEqual([track(2).uri, track(3).uri]);
    expect(playbackUris(track(1), list)).toEqual(list.map(item => item.uri));
    expect(playbackUris(track(3), list)).toEqual([track(3).uri]);
  });
  it("can still play a single track or a track outside the list", () => {
    expect(playbackUris(track(4))).toEqual([track(4).uri]);
    expect(playbackUris(track(4), list)).toEqual([track(4).uri]);
  });
});

describe("homepage Spotify pagination", () => {
  it("loads thirty tracks through three requests within Spotify's page limit", async () => {
    vi.mocked(searchSpotifyTracks).mockImplementation(async (_, __, offset = 0) => page(offset, offset + 10));
    const result = await loadSpotifyBatch("pop", new AbortController().signal);
    expect(result.items).toHaveLength(30);
    expect(result.next_offset).toBe(30);
    expect(vi.mocked(searchSpotifyTracks).mock.calls.map(call => call[2])).toEqual([0, 10, 20]);
  });
  it("stops at the final page and removes overlapping track IDs", async () => {
    vi.mocked(searchSpotifyTracks).mockResolvedValueOnce(page(0, 10)).mockResolvedValueOnce(page(5, null));
    const result = await loadSpotifyBatch("pop", new AbortController().signal);
    expect(result.items).toHaveLength(15);
    expect(result.next_offset).toBeNull();
    expect(mergeSpotifyTracks(result.items, [track(0)])).toHaveLength(15);
  });
  it("keeps loaded tracks and a retry offset if a later page fails", async () => {
    vi.mocked(searchSpotifyTracks).mockResolvedValueOnce(page(0, 10)).mockRejectedValueOnce(new Error("network"));
    const result = await loadSpotifyBatch("pop", new AbortController().signal);
    expect(result.items).toHaveLength(10);
    expect(result.next_offset).toBe(10);
    expect(result.warning).not.toBe("");
  });
  it("does not turn aborted requests into partial success", async () => {
    const controller = new AbortController();
    vi.mocked(searchSpotifyTracks).mockResolvedValueOnce(page(0, 10)).mockImplementationOnce(async () => {
      controller.abort(); throw new Error("aborted");
    });
    await expect(loadSpotifyBatch("pop", controller.signal)).rejects.toThrow("aborted");
  });
});
