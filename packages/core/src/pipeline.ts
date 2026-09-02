import { err, ok, type Result } from './result.ts';
import {
  dominantSpeakerSelector,
  type SelectionError,
  type SpeakerSegment,
  type SpeakerSelector,
} from './speaker.ts';

/** Stages as the user sees them on `--stages`. See the phase table in CLAUDE.md. */
export type PipelineStage =
  | 'decode'
  | 'denoise'
  | 'separate'
  | 'diarize'
  | 'extract'
  | 'transcribe';

export const PIPELINE_STAGES: readonly PipelineStage[] = [
  'decode',
  'denoise',
  'separate',
  'diarize',
  'extract',
  'transcribe',
] as const;

/**
 * What runs when `--stages` is not given. Transcription is deliberately absent:
 * it is slow, it is optional by design, and most runs only want clean audio.
 */
export const DEFAULT_STAGES: readonly PipelineStage[] = [
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
  'transcribe',
] as const;

/**
 * The pipeline works at 48 kHz because DeepFilterNet3 does, and decoding to a
 * lower rate first would throw away the band it is meant to clean. Stages that
 * need less — diarization runs at 16 kHz — resample on their own side; they
 * produce timestamps, so their rate must not constrain the audio anyone hears.
 */
export const DEFAULT_SAMPLE_RATE = 48_000;
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
  /** Carried by the extract call: what diarization found and who was chosen. */
  readonly segments?: readonly SpeakerSegment[];
  readonly speaker?: string;
}

/** One spoken line with its timing, as returned by transcription. */
export interface TranscriptLine {
  readonly startMs: number;
  readonly endMs: number;
  readonly text: string;
}

export interface EngineResponse {
  readonly outputPath: string;
  readonly segments: readonly SpeakerSegment[];
  readonly transcript: readonly TranscriptLine[];
  readonly warnings: readonly string[];
}

export type EngineError =
  | { kind: 'worker-unavailable'; detail: string }
  | { kind: 'model-gated'; model: string }
  | { kind: 'stage-failed'; stage: WorkerStage; detail: string }
  | { kind: 'unreadable-input'; detail: string }
  | { kind: 'silent-output'; detail: string }
  | { kind: 'write-failed'; detail: string }
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

export type PipelineError = DecodeError | EngineError | SelectionError;

export interface PipelineDeps {
  readonly decoder: AudioDecoder;
  readonly engine: VoiceEngine;
  readonly workspace: Workspace;
  /**
   * Which voice to keep. Defaults to the dominant-speaker heuristic; injecting
   * another one is how `--speaker <id>` will be added without touching this
   * orchestration.
   */
  readonly selector?: SpeakerSelector;
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
  readonly transcript: readonly TranscriptLine[];
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
      transcript: [],
      warnings: [],
    });
  }

  // Extraction is a second call. Diarization reports who speaks when, the
  // domain layer decides which voice to keep, and only then does the worker
  // mask the audio. Keeping that decision here is why `SpeakerSelector` exists.
  const extracting = workerStages.includes('extract');
  const transcribing = workerStages.includes('transcribe');
  const analysisStages = workerStages.filter(
    (stage) => stage !== 'extract' && stage !== 'transcribe',
  );

  // Transcription has to read the finished track, so it rides on whichever call
  // is the last one.
  const tail: readonly WorkerStage[] = transcribing ? ['transcribe'] : [];
  const firstCallStages: readonly WorkerStage[] = extracting
    ? analysisStages
    : [...analysisStages, ...tail];
  const secondCallStages: readonly WorkerStage[] = ['extract', ...tail];

  const analysisTarget = extracting
    ? await deps.workspace.createTempFile('-analysed.wav')
    : options.outputPath;

  const cleanUp = async (): Promise<void> => {
    await deps.workspace.remove(decodeTarget);
    if (extracting) await deps.workspace.remove(analysisTarget);
  };

  const warnings: string[] = [];
  let analysed = decoded.value.path;
  let segments: readonly SpeakerSegment[] = [];
  let transcript: readonly TranscriptLine[] = [];

  if (firstCallStages.length > 0) {
    const analysis = await deps.engine.run({
      inputPath: analysed,
      outputPath: analysisTarget,
      stages: firstCallStages,
    });

    if (!analysis.ok) {
      await cleanUp();
      return analysis;
    }

    analysed = analysis.value.outputPath;
    segments = analysis.value.segments;
    transcript = analysis.value.transcript;
    warnings.push(...analysis.value.warnings);
  }

  const selection =
    segments.length > 0 ? (deps.selector ?? dominantSpeakerSelector).select(segments) : null;

  if (!extracting) {
    await cleanUp();
    return ok({
      outputPath: firstCallStages.length > 0 ? analysed : options.outputPath,
      durationMs: decoded.value.durationMs,
      speakerId: selection?.ok ? selection.value : null,
      transcript,
      warnings,
    });
  }

  if (selection === null || !selection.ok) {
    await cleanUp();
    return err<SelectionError>({ kind: 'no-speech-detected' });
  }

  const extraction = await deps.engine.run({
    inputPath: analysed,
    outputPath: options.outputPath,
    stages: secondCallStages,
    segments,
    speaker: selection.value,
  });

  await cleanUp();

  if (!extraction.ok) return extraction;

  return ok({
    outputPath: extraction.value.outputPath,
    durationMs: decoded.value.durationMs,
    speakerId: selection.value,
    transcript: extraction.value.transcript.length > 0 ? extraction.value.transcript : transcript,
    warnings: [...warnings, ...extraction.value.warnings],
  });
}
