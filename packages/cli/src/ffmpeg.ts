import { resolve } from 'node:path';
import type { AudioDecoder, DecodedAudio, DecodeError, Result } from '@kov/core';
import { err, ok } from '@kov/core';
import type { ProcessOutcome, ProcessRunner } from './process.ts';

export interface FfmpegOptions {
  readonly ffmpegPath?: string;
  readonly ffprobePath?: string;
  readonly maxDurationMs?: number;
  readonly timeoutMs?: number;
}

const DEFAULT_MAX_DURATION_MS = 2 * 60 * 60 * 1_000;
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1_000;

interface ProbeStream {
  readonly codec_type?: string;
}

interface ProbeReport {
  readonly format?: { readonly duration?: string };
  readonly streams?: readonly ProbeStream[];
}

/** Maps the two failures that can happen to any spawned FFmpeg tool. */
const spawnFailure = (outcome: ProcessOutcome): DecodeError | null => {
  if (outcome.kind === 'not-found') return { kind: 'ffmpeg-missing' };
  if (outcome.kind === 'timeout') return { kind: 'timeout' };
  return null;
};

/**
 * Decodes any container FFmpeg understands into mono PCM at the requested rate.
 *
 * Paths are resolved to absolute before they reach the process, so a file named
 * `-y` cannot arrive as a flag, and the input is always passed behind `-i`.
 */
export function createFfmpegDecoder(
  runner: ProcessRunner,
  options: FfmpegOptions = {},
): AudioDecoder {
  const ffmpeg = options.ffmpegPath ?? 'ffmpeg';
  const ffprobe = options.ffprobePath ?? 'ffprobe';
  const maxDurationMs = options.maxDurationMs ?? DEFAULT_MAX_DURATION_MS;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  return {
    async decode(request): Promise<Result<DecodedAudio, DecodeError>> {
      const inputPath = resolve(request.inputPath);
      const outputPath = resolve(request.outputPath);

      const probe = await runner.run({
        command: ffprobe,
        args: [
          '-v',
          'error',
          '-print_format',
          'json',
          '-show_format',
          '-show_streams',
          '-i',
          inputPath,
        ],
        timeoutMs,
      });

      const probeFailure = spawnFailure(probe);
      if (probeFailure) return err(probeFailure);
      if (probe.kind !== 'exited') return err({ kind: 'ffmpeg-missing' });

      if (probe.code !== 0) {
        return err({ kind: 'unreadable-input', detail: probe.stderr.trim() || 'ffprobe failed' });
      }

      let report: ProbeReport;
      try {
        report = JSON.parse(probe.stdout) as ProbeReport;
      } catch {
        return err({ kind: 'unreadable-input', detail: 'ffprobe returned malformed JSON' });
      }

      const hasAudio = (report.streams ?? []).some((stream) => stream.codec_type === 'audio');
      if (!hasAudio) return err({ kind: 'no-audio-stream' });

      const durationSeconds = Number.parseFloat(report.format?.duration ?? '');
      if (!Number.isFinite(durationSeconds)) {
        return err({ kind: 'unreadable-input', detail: 'ffprobe reported no duration' });
      }

      const durationMs = Math.round(durationSeconds * 1_000);
      if (durationMs > maxDurationMs) {
        return err({ kind: 'too-long', durationMs, limitMs: maxDurationMs });
      }

      const decode = await runner.run({
        command: ffmpeg,
        args: [
          '-nostdin',
          '-v',
          'error',
          '-y',
          '-i',
          inputPath,
          '-vn',
          '-ac',
          String(request.channels),
          '-ar',
          String(request.sampleRate),
          '-c:a',
          'pcm_s16le',
          '-f',
          'wav',
          outputPath,
        ],
        timeoutMs,
      });

      const decodeFailure = spawnFailure(decode);
      if (decodeFailure) return err(decodeFailure);
      if (decode.kind !== 'exited') return err({ kind: 'ffmpeg-missing' });

      if (decode.code !== 0) {
        return err({ kind: 'decode-failed', detail: decode.stderr.trim() || 'ffmpeg failed' });
      }

      return ok({ path: outputPath, durationMs });
    },
  };
}
