#!/usr/bin/env bun
/**
 * Command line adapter. Parses arguments, wires the adapters into the domain
 * pipeline and renders the result. No audio logic lives here.
 */

import { PIPELINE_STAGES, runPipeline } from '@kov/core';
import { parseArgs } from './args.ts';
import { createFfmpegDecoder } from './ffmpeg.ts';
import { spawnRunner } from './process.ts';
import { describeError } from './render.ts';
import { formatTranscript } from './transcript.ts';
import { VERSION } from './version.ts';
import { createWorkerEngine } from './worker.ts';
import { resolveWorkerDir, workerDirCandidates } from './workerdir.ts';
import { createTempWorkspace } from './workspace.ts';

const USAGE = `kov — keep one voice

Usage:
  kov <input> [options]

Options:
  -o, --output <path>       Output file. Defaults to <input>.clean.wav
  -t, --transcript <path>   Write a transcript. Defaults to <output>.txt
  -s, --stages <list>       Comma separated stages to run.
                            Available: ${PIPELINE_STAGES.join(', ')}
  -h, --help                Show this message
  -v, --version             Show the version

Decoding always runs; --stages selects what happens after it.
Transcription is off by default: it is slow, and most runs only want the audio.
`;

export async function main(argv: readonly string[]): Promise<number> {
  const parsed = parseArgs(argv);

  if (!parsed.ok) {
    process.stderr.write(`error: ${parsed.error.message}\n\n${USAGE}`);
    return 2;
  }

  const options = parsed.value;

  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  if (options.version) {
    process.stdout.write(`${VERSION}\n`);
    return 0;
  }

  const worker = resolveWorkerDir(
    workerDirCandidates({
      env: process.env.KOV_WORKER_DIR,
      execPath: process.execPath,
      cwd: process.cwd(),
      moduleDir: import.meta.dir,
    }),
  );

  // Only decoding runs without the worker, so only then can a missing one be
  // ignored. Failing here beats a confusing error from `uv` further down.
  if (!worker.ok && options.stages.some((stage) => stage !== 'decode')) {
    process.stderr.write(`error: ${worker.detail}\n`);
    return 1;
  }

  const workerDir = worker.ok ? worker.path : '';
  const workspace = createTempWorkspace();

  try {
    const result = await runPipeline(
      {
        decoder: createFfmpegDecoder(spawnRunner),
        engine: createWorkerEngine(spawnRunner, { workerDir }),
        workspace,
      },
      {
        inputPath: options.input,
        outputPath: options.output,
        stages: options.stages,
      },
    );

    if (!result.ok) {
      process.stderr.write(`error: ${describeError(result.error)}\n`);
      return 1;
    }

    for (const warning of result.value.warnings) {
      process.stderr.write(`warning: ${warning}\n`);
    }

    if (result.value.speakerId !== null) {
      process.stderr.write(`speaker: kept ${result.value.speakerId}\n`);
    }

    if (options.transcript !== null) {
      if (result.value.transcript.length > 0) {
        await Bun.write(options.transcript, formatTranscript(result.value.transcript));
        process.stderr.write(`transcript: ${options.transcript}\n`);
      } else {
        process.stderr.write('warning: no speech was transcribed, so no transcript was written\n');
      }
    }

    process.stdout.write(`${result.value.outputPath}\n`);
    return 0;
  } finally {
    // Intermediate audio must not survive the run, successful or not.
    await workspace.dispose();
  }
}

if (import.meta.main) {
  process.exitCode = await main(process.argv.slice(2));
}
