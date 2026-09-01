import { ok, type Result } from './result.ts';
import { dominantSpeakerSelector, type SpeakerSegment } from './speaker.ts';

/** Stages as the user sees them on `--stages`. See the phase table in CLAUDE.md. */
export type PipelineStage = 'decode' | 'denoise' | 'separate' | 'diarize' | 'extract';

export const PIPELINE_STAGES: readonly PipelineStage[] = [
  'decode',
  'denoise',
  'separate',
  'diarize',
  'extract',
] as const;

/**
 * Stages the Python worker owns. `decode` is deliberately absent: FFmpeg is
 * invoked from the CLI so there is a single process-spawning surface to audit,
 * and so an unreadable file fails before torch is ever loaded.
 */
export type WorkerStage = Exclude<PipelineStage, 'decode'>;

export const WORKER_STAGES: readonly WorkerStage[] = [
  'denoise',
  'separate',
  'diarize',
  'extract',
] as const;

/** Every model in the pipeline expects mono PCM at this rate. */
export const DEFAULT_SAMPLE_RATE = 16_000;
export const DEFAULT_CHANNELS = 1;

// --- Decoder port -----------------------------------------------------------

export interface DecodeRequest {
  readonly inputPath: string;
  readonly outputPath: string;
  readonly sampleRate: number;
  readonly channels: number;
}

export interface DecodedAudio {
  readonly path: string;
  readonly durationMs: number;
}

export type DecodeError =
  | { kind: 'ffmpeg-missing' }
  | { kind: 'unreadable-input'; detail: string }
  | { kind: 'no-audio-stream' }
  | { kind: 'too-long'; durationMs: number; limitMs: number }
  | { kind: 'decode-failed'; detail: string }
  | { kind: 'timeout' };

export interface AudioDecoder {
  decode(request: DecodeRequest): Promise<Result<DecodedAudio, DecodeError>>;
}

// --- Engine port ------------------------------------------------------------

export interface EngineRequest {
  readonly inputPath: string;
  readonly outputPath: string;
  readonly stages: readonly WorkerStage[];
}

export interface EngineResponse {
  readonly outputPath: string;
  readonly segments: readonly SpeakerSegment[];
  readonly warnings: readonly string[];
}

export type EngineError =
  | { kind: 'worker-unavailable'; detail: string }
  | { kind: 'model-gated'; model: string }
  | { kind: 'stage-failed'; stage: WorkerStage; detail: string }
  | { kind: 'unreadable-input'; detail: string }
  | { kind: 'timeout' };

export interface VoiceEngine {
  run(request: EngineRequest): Promise<Result<EngineResponse, EngineError>>;
}

// --- Workspace port ---------------------------------------------------------

export interface Workspace {
  createTempFile(suffix: string): Promise<string>;
  remove(path: string): Promise<void>;
  /**
   * Removes everything the workspace created, including its directory.
   * The caller owns this lifecycle: `runPipeline` never disposes a workspace it
   * did not create, so a single workspace can span several runs.
   */
  dispose(): Promise<void>;
}

// --- Orchestration ----------------------------------------------------------

export type PipelineError = DecodeError | EngineError;

export interface PipelineDeps {
  readonly decoder: AudioDecoder;
  readonly engine: VoiceEngine;
  readonly workspace: Workspace;
}

export interface PipelineOptions {
  readonly inputPath: string;
  readonly outputPath: string;
  readonly stages: readonly PipelineStage[];
}

export interface PipelineOutcome {
  readonly outputPath: string;
  readonly durationMs: number;
  readonly speakerId: string | null;
  readonly warnings: readonly string[];
}

/**
 * Decoding always runs: every downstream stage needs mono PCM. When the caller
 * asks for `decode` alone the decoded file *is* the output and the worker is
 * never spawned, which keeps plain format conversion fast and dependency-free.
 */
export async function runPipeline(
  deps: PipelineDeps,
  options: PipelineOptions,
): Promise<Result<PipelineOutcome, PipelineError>> {
  const workerStages = options.stages.filter((stage): stage is WorkerStage => stage !== 'decode');
  const needsWorker = workerStages.length > 0;

  const decodeTarget = needsWorker
    ? await deps.workspace.createTempFile('.wav')
    : options.outputPath;

  const decoded = await deps.decoder.decode({
    inputPath: options.inputPath,
    outputPath: decodeTarget,
    sampleRate: DEFAULT_SAMPLE_RATE,
    channels: DEFAULT_CHANNELS,
  });

  if (!decoded.ok) {
    if (needsWorker) await deps.workspace.remove(decodeTarget);
    return decoded;
  }

  if (!needsWorker) {
    return ok({
      outputPath: options.outputPath,
      durationMs: decoded.value.durationMs,
      speakerId: null,
      warnings: [],
    });
  }

  const engineResult = await deps.engine.run({
    inputPath: decoded.value.path,
    outputPath: options.outputPath,
    stages: workerStages,
  });

  await deps.workspace.remove(decodeTarget);

  if (!engineResult.ok) return engineResult;

  // TODO(F3): the worker must be told which speaker to keep. That needs a
  // second call — diarize, select here, then extract — or selection moved into
  // the worker. For now the choice is reported, not acted upon.
  const selection =
    engineResult.value.segments.length > 0
      ? dominantSpeakerSelector.select(engineResult.value.segments)
      : null;

  return ok({
    outputPath: engineResult.value.outputPath,
    durationMs: decoded.value.durationMs,
    speakerId: selection?.ok ? selection.value : null,
    warnings: engineResult.value.warnings,
  });
}
