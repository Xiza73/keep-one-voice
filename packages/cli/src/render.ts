import type { PipelineError } from '@kov/core';

const formatDuration = (ms: number): string => {
  const totalSeconds = Math.round(ms / 1_000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
};

/**
 * Turns a pipeline failure into a line the user can act on. "spawn ENOENT" is
 * not an error message; "ffmpeg is not installed" is.
 */
export function describeError(error: PipelineError): string {
  switch (error.kind) {
    case 'ffmpeg-missing':
      return 'ffmpeg is not installed or not in PATH. Install it with: brew install ffmpeg';
    case 'unreadable-input':
      return `the input could not be read: ${error.detail}`;
    case 'no-audio-stream':
      return 'the input has no audio stream';
    case 'too-long':
      return `the input is ${formatDuration(error.durationMs)} long, over the ${formatDuration(
        error.limitMs,
      )} limit`;
    case 'decode-failed':
      return `ffmpeg could not decode the input: ${error.detail}`;
    case 'timeout':
      return 'the operation ran past its time budget and was stopped';
    case 'worker-unavailable':
      return `the python worker could not run: ${error.detail}. Set it up with: bun run setup:py`;
    case 'model-gated':
      return `the model ${error.model} is gated. Accept its licence on Hugging Face and export HF_TOKEN`;
    case 'stage-failed':
      return `stage "${error.stage}" failed: ${error.detail}`;
    case 'silent-output':
      return `the pipeline produced a silent track, which means a stage destroyed the audio: ${error.detail}`;
    case 'write-failed':
      return `the result could not be written: ${error.detail}`;
    case 'no-speech-detected':
      return 'no speech was detected, so there is no voice to keep. Run the diarize stage before extract';
  }
}
