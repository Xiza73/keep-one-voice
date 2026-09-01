/**
 * Domain layer for keep-one-voice.
 *
 * This package owns the pipeline contract and must not import anything from the
 * CLI adapter or from the Python worker adapter. Dependencies point inward.
 */

export * from './pipeline.ts';
export * from './result.ts';
export * from './speaker.ts';
