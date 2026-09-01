import { describe, expect, test } from 'bun:test';
import type { AudioDecoder, EngineRequest, VoiceEngine, Workspace } from './pipeline.ts';
import { runPipeline } from './pipeline.ts';
import { err, ok } from './result.ts';

const decoderThatSucceeds = (durationMs = 5_000): AudioDecoder => ({
  decode: async (request) => ok({ path: request.outputPath, durationMs }),
});

const engineThatSucceeds = (): { engine: VoiceEngine; calls: EngineRequest[] } => {
  const calls: EngineRequest[] = [];
  return {
    calls,
    engine: {
      run: async (request) => {
        calls.push(request);
        return ok({ outputPath: request.outputPath, segments: [], warnings: [] });
      },
    },
  };
};

const workspaceSpy = () => {
  const removed: string[] = [];
  let disposals = 0;
  const workspace: Workspace = {
    createTempFile: async (suffix) => `/tmp/kov-temp${suffix}`,
    remove: async (path) => {
      removed.push(path);
    },
    dispose: async () => {
      disposals += 1;
    },
  };
  return { workspace, removed, disposals: () => disposals };
};

describe('runPipeline', () => {
  test('writes the decoded audio straight to the output when only decode is requested', async () => {
    const { engine, calls } = engineThatSucceeds();
    const { workspace } = workspaceSpy();

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'note.wav', stages: ['decode'] },
    );

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.outputPath).toBe('note.wav');
    expect(calls).toHaveLength(0);
  });

  test('does not create a temporary file when only decode is requested', async () => {
    const { engine } = engineThatSucceeds();
    const { workspace, removed } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'note.wav', stages: ['decode'] },
    );

    expect(removed).toHaveLength(0);
  });

  test('hands the decoded temporary file to the engine and strips decode from its stages', async () => {
    const { engine, calls } = engineThatSucceeds();
    const { workspace } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      {
        inputPath: 'note.mp3',
        outputPath: 'clean.wav',
        stages: ['decode', 'denoise', 'extract'],
      },
    );

    expect(calls).toHaveLength(1);
    expect(calls[0]?.inputPath).toBe('/tmp/kov-temp.wav');
    expect(calls[0]?.outputPath).toBe('clean.wav');
    expect(calls[0]?.stages).toEqual(['denoise', 'extract']);
  });

  test('removes the temporary file after a successful run', async () => {
    const { engine } = engineThatSucceeds();
    const { workspace, removed } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'denoise'] },
    );

    expect(removed).toEqual(['/tmp/kov-temp.wav']);
  });

  test('removes the temporary file when the engine fails', async () => {
    const { workspace, removed } = workspaceSpy();
    const engine: VoiceEngine = {
      run: async () => err({ kind: 'worker-unavailable', detail: 'uv not found' }),
    };

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'denoise'] },
    );

    expect(result.ok).toBe(false);
    expect(removed).toEqual(['/tmp/kov-temp.wav']);
  });

  test('propagates a decode failure without calling the engine', async () => {
    const { engine, calls } = engineThatSucceeds();
    const { workspace } = workspaceSpy();
    const decoder: AudioDecoder = { decode: async () => err({ kind: 'ffmpeg-missing' }) };

    const result = await runPipeline(
      { decoder, engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'denoise'] },
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('ffmpeg-missing');
    expect(calls).toHaveLength(0);
  });

  test('reports the audio duration measured while decoding', async () => {
    const { engine } = engineThatSucceeds();
    const { workspace } = workspaceSpy();

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(12_345), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'note.wav', stages: ['decode'] },
    );

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.durationMs).toBe(12_345);
  });

  test('surfaces the warnings reported by the engine', async () => {
    const { workspace } = workspaceSpy();
    const engine: VoiceEngine = {
      run: async (request) =>
        ok({
          outputPath: request.outputPath,
          segments: [],
          warnings: ['stage "denoise" is not implemented yet'],
        }),
    };

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'denoise'] },
    );

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.warnings).toEqual(['stage "denoise" is not implemented yet']);
    }
  });

  test('selects the dominant speaker when the engine returns segments', async () => {
    const { workspace } = workspaceSpy();
    const engine: VoiceEngine = {
      run: async (request) =>
        ok({
          outputPath: request.outputPath,
          warnings: [],
          segments: [
            { speakerId: 'SPEAKER_00', startMs: 0, endMs: 1_000, meanDbfs: -20 },
            { speakerId: 'SPEAKER_01', startMs: 1_000, endMs: 6_000, meanDbfs: -20 },
          ],
        }),
    };

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'diarize'] },
    );

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.speakerId).toBe('SPEAKER_01');
  });

  test('reports no speaker when the engine returns no segments', async () => {
    const { engine } = engineThatSucceeds();
    const { workspace } = workspaceSpy();

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'denoise'] },
    );

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.speakerId).toBeNull();
  });

  test('never disposes the workspace: that lifecycle belongs to the caller', async () => {
    const { engine } = engineThatSucceeds();
    const { workspace, disposals } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'denoise'] },
    );

    expect(disposals()).toBe(0);
  });
});
