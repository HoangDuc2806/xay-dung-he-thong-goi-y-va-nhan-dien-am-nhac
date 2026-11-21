import { afterEach, expect, it, vi } from "vitest";
import { addQueuedTrack, readPlaybackQueue } from "./playback-queue";

afterEach(() => vi.unstubAllGlobals());

it("queues on the web device without replacing the playing track", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetcher);
  await addQueuedTrack("test", "device", "spotify:track:abc");
  const [url, options] = fetcher.mock.calls[0]!;
  expect(new URL(url).pathname).toBe("/v1/me/player/queue");
  expect(new URL(url).searchParams.get("device_id")).toBe("device");
  expect(new URL(url).searchParams.get("uri")).toBe("spotify:track:abc");
  expect(options.method).toBe("POST");
});

it("preserves Spotify queue order and repeated tracks", async () => {
  const a = { uri: "one", name: "First" }, b = { uri: "two", name: "Second" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ queue: [a, null, b, a] })));
  expect(await readPlaybackQueue("test", new AbortController().signal)).toEqual([a, b, a]);
});
