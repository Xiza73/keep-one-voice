import type {
  EngineError,
  EngineResponse,
  Result,
  SpeakerSegment,
  VoiceEngine,
  WorkerStage,
} from '@kov/core';
import { err, ok, WORKER_STAGES } from '@kov/core';
import type { ProcessRunner } from './process.ts';

export interface WorkerOptions {
  readonly workerDir: string;
  readonly command?: string;
  readonly timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 30 * 60 * 1_000;

interface RawSegment {
  readonly speaker_id?: unknown;
  readonly start_ms?: unknown;
  readonly end_ms?: unknown;
  readonly mean_dbfs?: unknown;
}

interface RawResponse {
  readonly ok?: unknown;
  readonly output_path?: unknown;
  readonly segments?: readonly RawSegment[];
  readonly warnings?: readonly unknown[];
  readonly error?: {
    readonly kind?: unknown;
    readonly detail?: unknown;
    readonly model?: unknown;
    readonly stage?: unknown;
  };
}

/** The worker writes one JSON object per line; anything else on stdout is noise. */
const lastJsonLine = (stdout: string): RawResponse | null => {
  const lines = stdout.split('\n');
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i]?.trim();
    if (!line) continue;
    try {
      return JSON.parse(line) as RawResponse;
    } catch {
      // Keep walking backwards: the worker may have logged before answering.
    }
  }
  return null;
};

const toSegment = (raw: RawSegment): SpeakerSegment => ({
  speakerId: String(raw.speaker_id ?? ''),
  startMs: Number(raw.start_ms ?? 0),
  endMs: Number(raw.end_ms ?? 0),
  meanDbfs: Number(raw.mean_dbfs ?? 0),
});

const asWorkerStage = (value: unknown): WorkerStage | null =>
  typeof value === 'string' && (WORKER_STAGES as readonly string[]).includes(value)
    ? (value as WorkerStage)
    : null;

const toEngineError = (raw: RawResponse['error']): EngineError => {
  const detail = typeof raw?.detail === 'string' ? raw.detail : 'the worker reported a failure';

  switch (raw?.kind) {
    case 'model-gated':
      return { kind: 'model-gated', model: String(raw.model ?? 'unknown model') };
    case 'unreadable-input':
      return { kind: 'unreadable-input', detail };
    case 'silent-output':
      return { kind: 'silent-output', detail };
    case 'write-failed':
      return { kind: 'write-failed', detail };
    case 'stage-failed': {
      const stage = asWorkerStage(raw.stage);
      // An unrecognised stage name means the two sides disagree about the
      // contract, which is a worker problem rather than a stage problem.
      return stage === null
        ? { kind: 'worker-unavailable', detail: `unknown stage in worker error: ${detail}` }
        : { kind: 'stage-failed', stage, detail };
    }
    default:
      return { kind: 'worker-unavailable', detail };
  }
};

/**
 * Runs the Python worker once per request: write one JSON line to stdin, read
 * one back from stdout. A persistent process would need request correlation by
 * id; a one-shot call does not, which is why the id is a constant here.
 */
export function createWorkerEngine(runner: ProcessRunner, options: WorkerOptions): VoiceEngine {
  const command = options.command ?? 'uv';
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  return {
    async run(request): Promise<Result<EngineResponse, EngineError>> {
      const payload = {
        id: '1',
        input_path: request.inputPath,
        output_path: request.outputPath,
        stages: request.stages as readonly WorkerStage[],
      };

      const outcome = await runner.run({
        command,
        args: ['run', '--project', options.workerDir, 'kov-worker'],
        stdin: `${JSON.stringify(payload)}\n`,
        timeoutMs,
      });

      if (outcome.kind === 'not-found') {
        return err({
          kind: 'worker-unavailable',
          detail: `${command} is not installed or not in PATH`,
        });
      }
      if (outcome.kind === 'timeout') return err({ kind: 'timeout' });

      const response = lastJsonLine(outcome.stdout);
      if (response === null) {
        return err({
          kind: 'worker-unavailable',
          detail: outcome.stderr.trim() || `the worker exited with code ${outcome.code}`,
        });
      }

      if (response.ok !== true) return err(toEngineError(response.error));

      return ok({
        outputPath: String(response.output_path ?? request.outputPath),
        segments: (response.segments ?? []).map(toSegment),
        warnings: (response.warnings ?? []).map(String),
      });
    },
  };
}
