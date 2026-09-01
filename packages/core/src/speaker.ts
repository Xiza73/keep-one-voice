import { err, ok, type Result } from './result.ts';

/** A contiguous span of speech attributed to a single speaker. */
export interface SpeakerSegment {
  readonly speakerId: string;
  readonly startMs: number;
  readonly endMs: number;
  /** Mean loudness of the segment, in dBFS (negative; 0 is full scale). */
  readonly meanDbfs: number;
}

export type SelectionError = { kind: 'no-speech-detected' };

/**
 * Chooses which speaker to keep. The MVP ships an automatic implementation,
 * but the port exists so `--speaker <id>` or reference-sample matching can be
 * added later without rewriting the pipeline.
 */
export interface SpeakerSelector {
  select(segments: readonly SpeakerSegment[]): Result<string, SelectionError>;
}

/**
 * Default selector: keep the speaker with the most total speaking time, and
 * break ties by mean loudness.
 *
 * Known limitation: this misfires when a secondary speaker talks longer or
 * louder than the intended one. It is a heuristic, not a guarantee.
 */
export const dominantSpeakerSelector: SpeakerSelector = {
  select(segments) {
    if (segments.length === 0) return err({ kind: 'no-speech-detected' });

    const totals = new Map<string, { durationMs: number; weightedDbfs: number }>();

    for (const segment of segments) {
      const durationMs = Math.max(0, segment.endMs - segment.startMs);
      const current = totals.get(segment.speakerId) ?? { durationMs: 0, weightedDbfs: 0 };
      totals.set(segment.speakerId, {
        durationMs: current.durationMs + durationMs,
        weightedDbfs: current.weightedDbfs + segment.meanDbfs * durationMs,
      });
    }

    let winnerId: string | undefined;
    let winnerDurationMs = -1;
    let winnerMeanDbfs = Number.NEGATIVE_INFINITY;

    for (const [speakerId, total] of totals) {
      const meanDbfs = total.durationMs > 0 ? total.weightedDbfs / total.durationMs : 0;
      const longer = total.durationMs > winnerDurationMs;
      const tiedButLouder = total.durationMs === winnerDurationMs && meanDbfs > winnerMeanDbfs;

      if (longer || tiedButLouder) {
        winnerId = speakerId;
        winnerDurationMs = total.durationMs;
        winnerMeanDbfs = meanDbfs;
      }
    }

    if (winnerId === undefined || winnerDurationMs <= 0) {
      return err({ kind: 'no-speech-detected' });
    }

    return ok(winnerId);
  },
};
