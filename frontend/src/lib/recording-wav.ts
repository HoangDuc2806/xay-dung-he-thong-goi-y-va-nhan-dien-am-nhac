/** PCM WAV upload for cloud recognition, decoded/resampled inside the browser. */
export function encodeMonoWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  if (!Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 96000) {
    throw new Error("Tần số lấy mẫu không hợp lệ.");
  }
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index++) view.setUint8(offset + index, value.charCodeAt(index));
  };
  text(0, "RIFF"); view.setUint32(4, buffer.byteLength - 8, true);
  text(8, "WAVE"); text(12, "fmt "); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let index = 0; index < samples.length; index++) {
    const raw = samples[index] ?? 0;
    const value = Number.isFinite(raw) ? Math.max(-1, Math.min(1, raw)) : 0;
    view.setInt16(44 + index * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
  }
  return buffer;
}

export async function recordingToWav(blob: Blob): Promise<File> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const duration = Math.min(decoded.duration, 15);
    if (!Number.isFinite(duration) || duration <= 0) throw new Error("Bản ghi không có âm thanh.");
    const rate = 16000;
    const offline = new OfflineAudioContext(1, Math.ceil(duration * rate), rate);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const mono = await offline.startRendering();
    return new File([encodeMonoWav(mono.getChannelData(0), rate)], `ghi-am-${Date.now()}.wav`, { type: "audio/wav" });
  } finally {
    await context.close().catch(() => undefined);
  }
}
