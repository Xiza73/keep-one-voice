import { describe, expect, test } from 'bun:test';
import { dominantSpeakerSelector, type SpeakerSegment } from './index.ts';

const segment = (
  speakerId: string,
  startMs: number,
  endMs: number,
  meanDbfs = -20,
): SpeakerSegment => ({ speakerId, startMs, endMs, meanDbfs });

describe('dominantSpeakerSelector', () => {
  test('reports no speech when there are no segments', () => {
    const result = dominantSpeakerSelector.select([]);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('no-speech-detected');
  });

  test('keeps the speaker with the most total speaking time', () => {
    const result = dominantSpeakerSelector.select([
      segment('A', 0, 1_000),
      segment('B', 1_000, 5_000),
      segment('A', 5_000, 6_000),
    ]);

    expect(result).toEqual({ ok: true, value: 'B' });
  });

  test('sums non-contiguous segments of the same speaker', () => {
    const result = dominantSpeakerSelector.select([
      segment('A', 0, 3_000),
      segment('B', 3_000, 7_000),
      segment('A', 7_000, 12_000),
    ]);

    expect(result).toEqual({ ok: true, value: 'A' });
  });

  test('breaks a duration tie by mean loudness', () => {
    const result = dominantSpeakerSelector.select([
      segment('A', 0, 2_000, -30),
      segment('B', 2_000, 4_000, -12),
    ]);

    expect(result).toEqual({ ok: true, value: 'B' });
  });

  test('reports no speech when every segment has zero duration', () => {
    const result = dominantSpeakerSelector.select([segment('A', 500, 500)]);

    expect(result.ok).toBe(false);
  });
});
