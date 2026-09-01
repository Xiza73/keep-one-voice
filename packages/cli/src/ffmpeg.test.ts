import { describe, expect, test } from 'bun:test';
import { createFfmpegDecoder } from './ffmpeg.ts';
import type { ProcessOutcome, ProcessRunner, ProcessSpec } from './process.ts';

const PROBE_OK = JSON.stringify({
  format: { duration: '12.345' },
  streams: [{ codec_type: 'audio', codec_name: 'mp3' }],
});

/** Replays a queued outcome per invocation and records every spec it received. */
const scriptedRunner = (outcomes: ProcessOutcome[]) => {
  const specs: ProcessSpec[] = [];
  const runner: ProcessRunner = {
    run: async (spec) => {
      specs.push(spec);
      return outcomes[specs.length - 1] ?? { kind: 'exited', code: 0, stdout: '', stderr: '' };
    },
  };
  return { runner, specs };
};

const exited = (code: number, stdout = '', stderr = ''): ProcessOutcome => ({
  kind: 'exited',
  code,
  stdout,
  stderr,
});

describe('createFfmpegDecoder', () => {
  test('probes the input before decoding it', async () => {
    const { runner, specs } = scriptedRunner([exited(0, PROBE_OK), exited(0)]);

    await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/note.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(specs).toHaveLength(2);
    expect(specs[0]?.command).toBe('ffprobe');
    expect(specs[1]?.command).toBe('ffmpeg');
  });

  test('asks ffmpeg for mono PCM at the requested sample rate', async () => {
    const { runner, specs } = scriptedRunner([exited(0, PROBE_OK), exited(0)]);

    await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/note.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    const args = specs[1]?.args ?? [];
    expect(args).toContain('-ac');
    expect(args[args.indexOf('-ac') + 1]).toBe('1');
    expect(args).toContain('-ar');
    expect(args[args.indexOf('-ar') + 1]).toBe('16000');
    expect(args).toContain('pcm_s16le');
  });

  test('passes the input behind -i so a leading dash cannot become a flag', async () => {
    const { runner, specs } = scriptedRunner([exited(0, PROBE_OK), exited(0)]);

    await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/-y.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    const args = specs[1]?.args ?? [];
    expect(args[args.indexOf('-i') + 1]).toBe('/audio/-y.mp3');
  });

  test('reports the duration read from the probe', async () => {
    const { runner } = scriptedRunner([exited(0, PROBE_OK), exited(0)]);

    const result = await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/note.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.durationMs).toBe(12_345);
  });

  test('reports ffmpeg-missing when the binary cannot be spawned', async () => {
    const { runner } = scriptedRunner([{ kind: 'not-found' }]);

    const result = await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/note.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('ffmpeg-missing');
  });

  test('rejects a file that carries no audio stream', async () => {
    const videoOnly = JSON.stringify({
      format: { duration: '4.0' },
      streams: [{ codec_type: 'video', codec_name: 'h264' }],
    });
    const { runner } = scriptedRunner([exited(0, videoOnly)]);

    const result = await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/clip.mp4',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('no-audio-stream');
  });

  test('rejects an unreadable input instead of trying to decode it', async () => {
    const { runner, specs } = scriptedRunner([exited(1, '', 'No such file or directory')]);

    const result = await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/missing.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('unreadable-input');
    expect(specs).toHaveLength(1);
  });

  test('refuses audio longer than the configured limit before decoding', async () => {
    const longProbe = JSON.stringify({
      format: { duration: '7200' },
      streams: [{ codec_type: 'audio' }],
    });
    const { runner, specs } = scriptedRunner([exited(0, longProbe)]);

    const result = await createFfmpegDecoder(runner, { maxDurationMs: 60_000 }).decode({
      inputPath: '/audio/long.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('too-long');
    expect(specs).toHaveLength(1);
  });

  test('reports a decode failure with the stderr ffmpeg produced', async () => {
    const { runner } = scriptedRunner([exited(0, PROBE_OK), exited(1, '', 'Invalid data found')]);

    const result = await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/broken.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('decode-failed');
      if (result.error.kind === 'decode-failed') {
        expect(result.error.detail).toContain('Invalid data found');
      }
    }
  });

  test('reports a timeout when ffmpeg exceeds its budget', async () => {
    const { runner } = scriptedRunner([exited(0, PROBE_OK), { kind: 'timeout' }]);

    const result = await createFfmpegDecoder(runner).decode({
      inputPath: '/audio/note.mp3',
      outputPath: '/tmp/out.wav',
      sampleRate: 16_000,
      channels: 1,
    });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('timeout');
  });
});
