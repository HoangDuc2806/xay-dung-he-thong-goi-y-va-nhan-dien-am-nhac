import type { LocalComparisonResponse } from "./api";

export type MicrophoneTrial = LocalComparisonResponse & { expected: string | null };

export function summarizeMicrophone(trials: MicrophoneTrial[], method: "landmark" | "mfcc_dtw") {
  let known = 0, correctKnown = 0, unknown = 0, falseAccepts = 0, elapsed = 0;
  for (const trial of trials) {
    const result = trial.results.find(row => row.method === method);
    if (!result) continue;
    elapsed += result.elapsed_ms;
    if (trial.expected === null) {
      unknown++;
      if (result.track_id !== null) falseAccepts++;
    } else {
      known++;
      if (result.track_id === trial.expected) correctKnown++;
    }
  }
  const total = known + unknown;
  return { method, total, known, correctKnown, unknown, falseAccepts,
    correct: correctKnown + unknown - falseAccepts, meanProcessingMs: total ? Math.round(elapsed / total) : null };
}
