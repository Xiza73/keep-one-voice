import { describe, expect, test } from 'bun:test';
import { parseArgs } from './args.ts';

describe('parseArgs', () => {
  test('fails when no input file is given', () => {
    const result = parseArgs([]);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toBe('missing input file');
  });

  test('derives the output path from the input when --output is omitted', () => {
    const result = parseArgs(['interview.mp3']);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.output).toBe('interview.clean.wav');
  });

  test('honours an explicit --output', () => {
    const result = parseArgs(['interview.mp3', '--output', 'voice.wav']);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.output).toBe('voice.wav');
  });

  test('runs every stage except transcription by default', () => {
    const result = parseArgs(['note.ogg']);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.stages).toEqual(['decode', 'denoise', 'separate', 'diarize', 'extract']);
    }
  });

  test('does not transcribe unless asked', () => {
    const result = parseArgs(['note.ogg']);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.transcript).toBeNull();
  });

  test('asking for a transcript path implies the transcribe stage', () => {
    const result = parseArgs(['note.ogg', '--transcript', 'words.txt']);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.stages).toContain('transcribe');
      expect(result.value.transcript).toBe('words.txt');
    }
  });

  test('asking for the transcribe stage derives a transcript path', () => {
    const result = parseArgs(['interview.mp3', '--stages', 'decode,transcribe']);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.transcript).toBe('interview.clean.txt');
  });

  test('does not add transcribe twice when both are given', () => {
    const result = parseArgs([
      'note.ogg',
      '--stages',
      'decode,transcribe',
      '--transcript',
      'words.txt',
    ]);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.stages.filter((stage) => stage === 'transcribe')).toHaveLength(1);
    }
  });

  test('rejects a transcript flag with no path', () => {
    const result = parseArgs(['note.ogg', '--transcript']);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toBe('--transcript requires a path');
  });

  test('accepts a comma separated stage subset', () => {
    const result = parseArgs(['note.ogg', '--stages', 'decode,denoise']);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.stages).toEqual(['decode', 'denoise']);
  });

  test('rejects an unknown stage', () => {
    const result = parseArgs(['note.ogg', '--stages', 'decode,translate']);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toBe('unknown stage(s): translate');
  });

  test('rejects a flag that is missing its value', () => {
    const result = parseArgs(['note.ogg', '--output']);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toBe('--output requires a path');
  });

  test('rejects a second input file', () => {
    const result = parseArgs(['a.mp3', 'b.mp3']);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toBe('only one input file is supported');
  });

  test('short circuits on --help', () => {
    const result = parseArgs(['--help']);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.help).toBe(true);
  });
});
