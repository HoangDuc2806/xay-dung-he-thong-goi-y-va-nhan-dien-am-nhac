import { expect, it } from "vitest";
import { summarizeMicrophone, type MicrophoneTrial } from "./microphone-evaluation";

it("counts known matches and correct rejections separately for each matcher", () => {
  function trial(expected: string | null, predicted: string | null): MicrophoneTrial {
    return { expected, duration_seconds: 12, results: [
      { method: "landmark", track_id: predicted, track: null, elapsed_ms: 40 },
      { method: "mfcc_dtw", track_id: null, track: null, elapsed_ms: 80 },
    ] };
  }
  const recordings = [trial("A", "A"), trial("A", "B"), trial("B", null), trial(null, null), trial(null, "A")];
  expect(summarizeMicrophone(recordings, "landmark")).toMatchObject({
    total: 5, known: 3, correctKnown: 1, unknown: 2, falseAccepts: 1, correct: 2, meanProcessingMs: 40,
  });
  expect(summarizeMicrophone(recordings, "mfcc_dtw")).toMatchObject({
    correctKnown: 0, falseAccepts: 0, correct: 2, meanProcessingMs: 80,
  });
});
