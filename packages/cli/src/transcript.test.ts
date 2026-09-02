import { describe, expect, test } from 'bun:test';
import { formatTranscript, timestamp } from './transcript.ts';

const line = (startMs: number, endMs: number, text: string) => ({ startMs, endMs, text });

describe('timestamp', () => {
  test('renders zero with every field padded', () => {
    expect(timestamp(0)).toBe('00:00:00.000');
  });

  test('keeps milliseconds', () => {
    expect(timestamp(1_240)).toBe('00:00:01.240');
  });

  test('rolls over into minutes', () => {
    expect(timestamp(61_000)).toBe('00:01:01.000');
  });

  test('rolls over into hours', () => {
    expect(timestamp(3_723_450)).toBe('01:02:03.450');
  });

  test('clamps a negative time to zero', () => {
    expect(timestamp(-5)).toBe('00:00:00.000');
  });
});

describe('formatTranscript', () => {
  test('renders nothing when there is nothing to render', () => {
    expect(formatTranscript([])).toBe('');
  });

  test('puts the start time in front of each line', () => {
    const text = formatTranscript([line(1_240, 4_000, 'the window was open')]);

    expect(text).toBe('[00:00:01.240] the window was open\n');
  });

  test('keeps one line per segment, in order', () => {
    const text = formatTranscript([line(0, 1_000, 'first'), line(1_000, 2_000, 'second')]);

    expect(text.trimEnd().split('\n')).toEqual(['[00:00:00.000] first', '[00:00:01.000] second']);
  });

  test('trims padding around the spoken text', () => {
    const text = formatTranscript([line(0, 1_000, '   spaced out   ')]);

    expect(text).toBe('[00:00:00.000] spaced out\n');
  });

  test('ends with a newline so the file is well formed', () => {
    expect(formatTranscript([line(0, 1_000, 'x')])).toEndWith('\n');
  });
});
