import { describe, expect, test } from 'bun:test';
import type {
  AudioDecoder,
  DecodeRequest,
  EngineRequest,
  VoiceEngine,
  Workspace,
} from './pipeline.ts';
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
        stages: ['decode', 'denoise', 'separate'],
      },
    );

    expect(calls).toHaveLength(1);
    expect(calls[0]?.inputPath).toBe('/tmp/kov-temp.wav');
    expect(calls[0]?.outputPath).toBe('clean.wav');
    expect(calls[0]?.stages).toEqual(['denoise', 'separate']);
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

  test('asks the decoder for mono audio at the pipeline sample rate', async () => {
    const requests: DecodeRequest[] = [];
    const decoder: AudioDecoder = {
      decode: async (request) => {
        requests.push(request);
        return ok({ path: request.outputPath, durationMs: 1_000 });
      },
    };
    const { engine } = engineThatSucceeds();
    const { workspace } = workspaceSpy();

    await runPipeline(
      { decoder, engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'note.wav', stages: ['decode'] },
    );

    expect(requests[0]?.sampleRate).toBe(48_000);
    expect(requests[0]?.channels).toBe(1);
  });

  test('splits extraction into a second call, after diarization', async () => {
    const segments = [
      { speakerId: 'SPEAKER_00', startMs: 0, endMs: 1_000, meanDbfs: -20 },
      { speakerId: 'SPEAKER_01', startMs: 1_000, endMs: 6_000, meanDbfs: -20 },
    ];
    const calls: EngineRequest[] = [];
    const engine: VoiceEngine = {
      run: async (request) => {
        calls.push(request);
        return ok({
          outputPath: request.outputPath,
          warnings: [],
          segments: request.stages.includes('diarize') ? segments : [],
        });
      },
    };
    const { workspace } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      {
        inputPath: 'note.mp3',
        outputPath: 'clean.wav',
        stages: ['decode', 'denoise', 'diarize', 'extract'],
      },
    );

    expect(calls).toHaveLength(2);
    expect(calls[0]?.stages).toEqual(['denoise', 'diarize']);
    expect(calls[1]?.stages).toEqual(['extract']);
  });

  test('hands the chosen speaker and the segments to the extract call', async () => {
    const segments = [
      { speakerId: 'SPEAKER_00', startMs: 0, endMs: 1_000, meanDbfs: -20 },
      { speakerId: 'SPEAKER_01', startMs: 1_000, endMs: 6_000, meanDbfs: -20 },
    ];
    const calls: EngineRequest[] = [];
    const engine: VoiceEngine = {
      run: async (request) => {
        calls.push(request);
        return ok({
          outputPath: request.outputPath,
          warnings: [],
          segments: request.stages.includes('diarize') ? segments : [],
        });
      },
    };
    const { workspace } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'diarize', 'extract'] },
    );

    expect(calls[1]?.speaker).toBe('SPEAKER_01');
    expect(calls[1]?.segments).toEqual(segments);
  });

  test('feeds the analysed audio into the extract call, not the raw decode', async () => {
    const calls: EngineRequest[] = [];
    const engine: VoiceEngine = {
      run: async (request) => {
        calls.push(request);
        return ok({
          outputPath: request.outputPath,
          warnings: [],
          segments: request.stages.includes('diarize')
            ? [{ speakerId: 'A', startMs: 0, endMs: 1_000, meanDbfs: -20 }]
            : [],
        });
      },
    };
    const { workspace } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'diarize', 'extract'] },
    );

    expect(calls[1]?.inputPath).toBe('/tmp/kov-temp-analysed.wav');
  });

  test('uses an injected selector instead of the dominance heuristic', async () => {
    const segments = [
      { speakerId: 'SPEAKER_00', startMs: 0, endMs: 1_000, meanDbfs: -20 },
      { speakerId: 'SPEAKER_01', startMs: 1_000, endMs: 6_000, meanDbfs: -20 },
    ];
    const calls: EngineRequest[] = [];
    const engine: VoiceEngine = {
      run: async (request) => {
        calls.push(request);
        return ok({
          outputPath: request.outputPath,
          warnings: [],
          segments: request.stages.includes('diarize') ? segments : [],
        });
      },
    };
    const { workspace } = workspaceSpy();

    // This is how `--speaker <id>` will arrive: a different selector, nothing else.
    const result = await runPipeline(
      {
        decoder: decoderThatSucceeds(),
        engine,
        workspace,
        selector: { select: () => ok('SPEAKER_00') },
      },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'diarize', 'extract'] },
    );

    expect(calls[1]?.speaker).toBe('SPEAKER_00');
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.speakerId).toBe('SPEAKER_00');
  });

  test('refuses to extract when diarization found nobody', async () => {
    const { engine, calls } = engineThatSucceeds();
    const { workspace } = workspaceSpy();

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'extract'] },
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('no-speech-detected');
    expect(calls).toHaveLength(0);
  });

  test('removes both temporary files after an extraction run', async () => {
    const engine: VoiceEngine = {
      run: async (request) =>
        ok({
          outputPath: request.outputPath,
          warnings: [],
          segments: request.stages.includes('diarize')
            ? [{ speakerId: 'A', startMs: 0, endMs: 1_000, meanDbfs: -20 }]
            : [],
        }),
    };
    const { workspace, removed } = workspaceSpy();

    await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'diarize', 'extract'] },
    );

    expect(removed).toEqual(['/tmp/kov-temp.wav', '/tmp/kov-temp-analysed.wav']);
  });

  test('collects the warnings of both calls', async () => {
    const engine: VoiceEngine = {
      run: async (request) =>
        ok({
          outputPath: request.outputPath,
          warnings: [`warned by ${request.stages.join(',')}`],
          segments: request.stages.includes('diarize')
            ? [{ speakerId: 'A', startMs: 0, endMs: 1_000, meanDbfs: -20 }]
            : [],
        }),
    };
    const { workspace } = workspaceSpy();

    const result = await runPipeline(
      { decoder: decoderThatSucceeds(), engine, workspace },
      { inputPath: 'note.mp3', outputPath: 'clean.wav', stages: ['decode', 'diarize', 'extract'] },
    );

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.warnings).toEqual(['warned by diarize', 'warned by extract']);
    }
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
