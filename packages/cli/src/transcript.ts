import type { TranscriptLine } from '@kov/core';

/** `hh:mm:ss.mmm`, so a quote can be found in the audio it came from. */
export function timestamp(ms: number): string {
  const clamped = Math.max(0, Math.round(ms));
  const millis = clamped % 1_000;
  const totalSeconds = Math.floor(clamped / 1_000);
  const seconds = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3_600);

  const pad = (value: number, width = 2): string => String(value).padStart(width, '0');

  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}.${pad(millis, 3)}`;
}

/**
 * One line per spoken segment, prefixed with when it starts.
 *
 * Plain text rather than SRT: this is for reading and quoting, and a timestamp
 * in front of each line makes a quote findable without a subtitle player.
 */
export function formatTranscript(lines: readonly TranscriptLine[]): string {
  if (lines.length === 0) return '';

  return `${lines.map((line) => `[${timestamp(line.startMs)}] ${line.text.trim()}`).join('\n')}\n`;
}
