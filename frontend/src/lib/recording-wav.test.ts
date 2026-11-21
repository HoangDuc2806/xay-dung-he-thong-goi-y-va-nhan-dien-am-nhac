import { describe, expect, it } from "vitest";
import { encodeMonoWav } from "./recording-wav";

describe("microphone PCM WAV upload", () => {
  it("writes a decodable mono 16-bit PCM header and bounds sample amplitudes", () => {
    const samples = new Float32Array([-2, -1, 0, 1, 2, NaN]);
    const data = encodeMonoWav(samples, 16000);
    const view = new DataView(data);
    expect(new TextDecoder().decode(data.slice(0, 4))).toBe("RIFF");
    expect(new TextDecoder().decode(data.slice(8, 12))).toBe("WAVE");
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(28, true)).toBe(32000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(samples.length * 2);
    expect(view.getInt16(44, true)).toBe(-32768);
    expect(view.getInt16(50, true)).toBe(32767);
    expect(view.getInt16(54, true)).toBe(0);
  });
  it("rejects an invalid sample rate", () => {
    expect(() => encodeMonoWav(new Float32Array(1), 0)).toThrow();
  });
});
