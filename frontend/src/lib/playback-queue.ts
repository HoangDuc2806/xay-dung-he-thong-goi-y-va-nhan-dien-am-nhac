export type QueueItem = {
  uri: string; name: string; artists?: { name: string }[];
  album?: { images?: { url: string }[] }; show?: { name: string }; images?: { url: string }[];
};

const endpoint = "https://api.spotify.com/v1/me/player/queue";

export async function addQueuedTrack(token: string, device: string, uri: string) {
  const params = new URLSearchParams({ uri, device_id: device });
  const response = await fetch(`${endpoint}?${params}`, {
    method: "POST", headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(response.status === 429
    ? "Spotify đang giới hạn yêu cầu. Vui lòng thử lại sau."
    : "Spotify chưa thêm được bài. Kiểm tra kết nối và thiết bị đang phát.");
}

export async function readPlaybackQueue(token: string, signal: AbortSignal): Promise<QueueItem[]> {
  const response = await fetch(endpoint, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal,
  });
  if (!response.ok) throw new Error("Không đọc được danh sách chờ từ Spotify.");
  if (response.status === 204) return [];
  const data: { queue?: (QueueItem | null)[] } = await response.json();
  return (data.queue ?? []).filter((item): item is QueueItem => Boolean(item?.uri && item.name));
}
