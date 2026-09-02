import {
  DEFAULT_STAGES,
  err,
  ok,
  PIPELINE_STAGES,
  type PipelineStage,
  type Result,
} from '@kov/core';

export interface CliOptions {
  readonly input: string;
  readonly output: string;
  readonly stages: readonly PipelineStage[];
  readonly transcript: string | null;
  readonly help: boolean;
  readonly version: boolean;
}

const EMPTY: CliOptions = {
  input: '',
  output: '',
  stages: DEFAULT_STAGES,
  transcript: null,
  help: false,
  version: false,
};

const isStage = (value: string): value is PipelineStage =>
  (PIPELINE_STAGES as readonly string[]).includes(value);

const withoutExtension = (path: string): string => path.replace(/\.[^./]+$/, '');

const defaultOutputFor = (input: string): string => `${withoutExtension(input)}.clean.wav`;

const defaultTranscriptFor = (output: string): string => `${withoutExtension(output)}.txt`;

export function parseArgs(argv: readonly string[]): Result<CliOptions> {
  let input: string | undefined;
  let output: string | undefined;
  let transcript: string | undefined;
  let stages: readonly PipelineStage[] = DEFAULT_STAGES;

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

      case '-t':
      case '--transcript': {
        i += 1;
        const value = argv[i];
        if (value === undefined) return err(new Error('--transcript requires a path'));
        transcript = value;
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

  const resolvedOutput = output ?? defaultOutputFor(input);

  // The two ways of asking for a transcript imply each other: a path means run
  // the stage, and the stage means write somewhere sensible.
  const resolvedStages =
    transcript !== undefined && !stages.includes('transcribe')
      ? [...stages, 'transcribe' as const]
      : stages;

  const resolvedTranscript = resolvedStages.includes('transcribe')
    ? (transcript ?? defaultTranscriptFor(resolvedOutput))
    : null;

  return ok({
    input,
    output: resolvedOutput,
    stages: resolvedStages,
    transcript: resolvedTranscript,
    help: false,
    version: false,
  });
}
