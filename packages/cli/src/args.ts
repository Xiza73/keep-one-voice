import { err, ok, PIPELINE_STAGES, type PipelineStage, type Result } from '@kov/core';

export interface CliOptions {
  readonly input: string;
  readonly output: string;
  readonly stages: readonly PipelineStage[];
  readonly help: boolean;
  readonly version: boolean;
}

const EMPTY: CliOptions = {
  input: '',
  output: '',
  stages: PIPELINE_STAGES,
  help: false,
  version: false,
};

const isStage = (value: string): value is PipelineStage =>
  (PIPELINE_STAGES as readonly string[]).includes(value);

const defaultOutputFor = (input: string): string => `${input.replace(/\.[^./]+$/, '')}.clean.wav`;

export function parseArgs(argv: readonly string[]): Result<CliOptions> {
  let input: string | undefined;
  let output: string | undefined;
  let stages: readonly PipelineStage[] = PIPELINE_STAGES;

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] as string;

    switch (arg) {
      case '-h':
      case '--help':
        return ok({ ...EMPTY, help: true });

      case '-v':
      case '--version':
        return ok({ ...EMPTY, version: true });

      case '-o':
      case '--output': {
        i += 1;
        const value = argv[i];
        if (value === undefined) return err(new Error(`${arg} requires a path`));
        output = value;
        break;
      }

      case '-s':
      case '--stages': {
        i += 1;
        const value = argv[i];
        if (value === undefined) return err(new Error(`${arg} requires a stage list`));

        const requested = value.split(',').map((stage) => stage.trim());
        const unknown = requested.filter((stage) => !isStage(stage));
        if (unknown.length > 0) {
          return err(new Error(`unknown stage(s): ${unknown.join(', ')}`));
        }
        stages = requested as PipelineStage[];
        break;
      }

      default:
        if (arg.startsWith('-')) return err(new Error(`unknown option: ${arg}`));
        if (input !== undefined) return err(new Error('only one input file is supported'));
        input = arg;
    }
  }

  if (input === undefined) return err(new Error('missing input file'));

  return ok({
    input,
    output: output ?? defaultOutputFor(input),
    stages,
    help: false,
    version: false,
  });
}
