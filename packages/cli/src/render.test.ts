import { describe, expect, test } from 'bun:test';
import { describeError } from './render.ts';

describe('describeError', () => {
  test('tells the user how to install ffmpeg when it is missing', () => {
    expect(describeError({ kind: 'ffmpeg-missing' })).toContain('brew install ffmpeg');
  });

  test('tells the user how to set up the worker when it cannot run', () => {
    const message = describeError({ kind: 'worker-unavailable', detail: 'uv not found' });

    expect(message).toContain('uv not found');
    expect(message).toContain('bun run setup:py');
  });

  test('names the gated model and the environment variable it needs', () => {
    const message = describeError({
      kind: 'model-gated',
      model: 'pyannote/speaker-diarization-3.1',
    });

    expect(message).toContain('pyannote/speaker-diarization-3.1');
    expect(message).toContain('HF_TOKEN');
  });

  test('reports both the duration and the limit in human units', () => {
    const message = describeError({ kind: 'too-long', durationMs: 7_200_000, limitMs: 60_000 });

    expect(message).toContain('120m 0s');
    expect(message).toContain('1m 0s');
  });

  test('keeps the ffmpeg stderr when decoding fails', () => {
    const message = describeError({ kind: 'decode-failed', detail: 'Invalid data found' });

    expect(message).toContain('Invalid data found');
  });

  test('never renders an empty message', () => {
    const errors = [
      { kind: 'ffmpeg-missing' },
      { kind: 'no-audio-stream' },
      { kind: 'timeout' },
      { kind: 'unreadable-input', detail: 'x' },
      { kind: 'decode-failed', detail: 'x' },
      { kind: 'too-long', durationMs: 1, limitMs: 1 },
      { kind: 'worker-unavailable', detail: 'x' },
      { kind: 'model-gated', model: 'x' },
      { kind: 'stage-failed', stage: 'denoise', detail: 'x' },
      { kind: 'silent-output', detail: 'x' },
      { kind: 'write-failed', detail: 'x' },
      { kind: 'no-speech-detected' },
    ] as const;

    for (const error of errors) {
      expect(describeError(error).length).toBeGreaterThan(0);
    }
  });
});
