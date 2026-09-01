#!/usr/bin/env bun
/**
 * Command line adapter. Parses arguments, delegates to the domain layer and
 * renders results. No audio logic lives here.
 */

import { PIPELINE_STAGES, type PipelineStage } from '@kov/core';
import { parseArgs } from './args.ts';

const USAGE = `kov — keep one voice

Usage:
  kov <input> [options]

Options:
  -o, --output <path>   Output file. Defaults to <input>.clean.wav
  -s, --stages <list>   Comma separated stages to run.
                        Available: ${PIPELINE_STAGES.join(', ')}
  -h, --help            Show this message
  -v, --version         Show the version
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
    process.stdout.write('0.0.0\n');
    return 0;
  }

  // TODO(F0): wire the Python worker adapter and run the pipeline.
  process.stderr.write(
    `not implemented yet: would process "${options.input}" ` +
      `through [${(options.stages satisfies readonly PipelineStage[]).join(', ')}]\n`,
  );
  return 1;
}

if (import.meta.main) {
  process.exitCode = await main(process.argv.slice(2));
}
