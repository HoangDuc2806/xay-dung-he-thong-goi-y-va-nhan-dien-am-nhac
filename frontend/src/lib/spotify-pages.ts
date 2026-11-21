import { searchSpotifyTracks, type SpotifyTrack } from "./api";

export type SpotifyBatch = { items: SpotifyTrack[]; next_offset: number | null; warning: string };

/** Start the URI queue at the clicked row. Earlier rows remain available in the app. */
export function playbackUris(track: SpotifyTrack, list?: SpotifyTrack[]): string[] {
  const index = list?.findIndex(item => item.uri === track.uri) ?? -1;
  return list && index >= 0 ? list.slice(index).map(item => item.uri) : [track.uri];
}

export function mergeSpotifyTracks(previous: SpotifyTrack[], incoming: SpotifyTrack[]): SpotifyTrack[] {
  const unique = new Map(previous.map(track => [track.id, track]));
  for (const track of incoming) unique.set(track.id, track);
  return [...unique.values()];
}

/** Spotify allows ten results per request; fetch at most three consecutive pages. */
export async function loadSpotifyBatch(query: string, signal: AbortSignal, offset=0): Promise<SpotifyBatch> {
  let items: SpotifyTrack[] = [];
  let next: number | null = offset;
  for (let index = 0; index < 3 && next !== null; index++) {
    const pageOffset: number = next;
    try {
      const page = await searchSpotifyTracks(query, signal, pageOffset);
      items = mergeSpotifyTracks(items, page.items);
      const following = page.next_offset;
      // Guard against malformed/stale pagination metadata; never loop one page.
      next = typeof following === "number" && Number.isInteger(following)
        && following > pageOffset && following <= 1000 ? following : null;
    } catch (error) {
      if (signal.aborted || index === 0) throw error;
      return { items, next_offset: pageOffset, warning: "Mới tải được một phần danh sách. Bấm Tải thêm để thử tiếp." };
    }
  }
  return { items, next_offset: next, warning: "" };
}
