import { describe, expect, test } from 'bun:test';
import type { ProcessOutcome, ProcessRunner, ProcessSpec } from './process.ts';
import { createWorkerEngine } from './worker.ts';

const scriptedRunner = (outcome: ProcessOutcome) => {
  const specs: ProcessSpec[] = [];
  const runner: ProcessRunner = {
    run: async (spec) => {
      specs.push(spec);
      return outcome;
    },
  };
  return { runner, specs };
};

const responseLine = (payload: Record<string, unknown>) => `${JSON.stringify(payload)}\n`;

const okResponse = responseLine({
  id: 'req-1',
  ok: true,
  output_path: '/tmp/clean.wav',
  segments: [],
  warnings: [],
});

const request = {
  inputPath: '/tmp/decoded.wav',
  outputPath: '/tmp/clean.wav',
  stages: ['denoise'] as const,
};

describe('createWorkerEngine', () => {
  test('sends exactly one JSON line on stdin', async () => {
    const { runner, specs } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: okResponse,
      stderr: '',
    });

    await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    const stdin = specs[0]?.stdin ?? '';
    expect(stdin.trimEnd().split('\n')).toHaveLength(1);
    expect(JSON.parse(stdin)).toMatchObject({
      input_path: '/tmp/decoded.wav',
      output_path: '/tmp/clean.wav',
      stages: ['denoise'],
    });
  });

  test('runs the worker through uv inside the worker project', async () => {
    const { runner, specs } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: okResponse,
      stderr: '',
    });

    await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(specs[0]?.command).toBe('uv');
    expect(specs[0]?.args).toEqual(['run', '--project', '/repo/worker', 'kov-worker']);
  });

  test('returns the parsed response on success', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: responseLine({
        id: 'req-1',
        ok: true,
        output_path: '/tmp/clean.wav',
        warnings: ['stage "denoise" is not implemented yet'],
        segments: [{ speaker_id: 'SPEAKER_00', start_ms: 0, end_ms: 900, mean_dbfs: -18.5 }],
      }),
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.outputPath).toBe('/tmp/clean.wav');
      expect(result.value.warnings).toEqual(['stage "denoise" is not implemented yet']);
      expect(result.value.segments).toEqual([
        { speakerId: 'SPEAKER_00', startMs: 0, endMs: 900, meanDbfs: -18.5 },
      ]);
    }
  });

  test('maps a gated model error onto the domain error', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: responseLine({
        id: 'req-1',
        ok: false,
        error: { kind: 'model-gated', model: 'pyannote/speaker-diarization-3.1' },
      }),
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('model-gated');
      if (result.error.kind === 'model-gated') {
        expect(result.error.model).toBe('pyannote/speaker-diarization-3.1');
      }
    }
  });

  test('keeps the stage the worker reported on a stage failure', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: responseLine({
        id: 'req-1',
        ok: false,
        error: { kind: 'stage-failed', stage: 'separate', detail: 'out of memory' },
      }),
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok && result.error.kind === 'stage-failed') {
      expect(result.error.stage).toBe('separate');
      expect(result.error.detail).toBe('out of memory');
    } else {
      throw new Error('expected a stage-failed error');
    }
  });

  test('treats an unrecognised stage name as a contract mismatch', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: responseLine({
        id: 'req-1',
        ok: false,
        error: { kind: 'stage-failed', stage: 'translate', detail: 'boom' },
      }),
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('worker-unavailable');
  });

  test('maps a silent output onto the domain error', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: responseLine({
        id: 'req-1',
        ok: false,
        error: { kind: 'silent-output', detail: 'after: denoise' },
      }),
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('silent-output');
  });

  test('maps a write failure onto the domain error', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: responseLine({
        id: 'req-1',
        ok: false,
        error: { kind: 'write-failed', detail: 'no space left on device' },
      }),
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('write-failed');
  });

  test('reports worker-unavailable when uv is not installed', async () => {
    const { runner } = scriptedRunner({ kind: 'not-found' });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('worker-unavailable');
  });

  test('reports worker-unavailable when the process exits without a response', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 1,
      stdout: '',
      stderr: 'ModuleNotFoundError: No module named soundfile',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('worker-unavailable');
      if (result.error.kind === 'worker-unavailable') {
        expect(result.error.detail).toContain('soundfile');
      }
    }
  });

  test('reports worker-unavailable when stdout is not valid JSON', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: 'not json at all\n',
      stderr: '',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('worker-unavailable');
  });

  test('ignores log noise and reads the last JSON line of stdout', async () => {
    const { runner } = scriptedRunner({
      kind: 'exited',
      code: 0,
      stdout: `\n${okResponse}`,
      stderr: 'loading model...',
    });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(true);
  });

  test('reports a timeout when the worker exceeds its budget', async () => {
    const { runner } = scriptedRunner({ kind: 'timeout' });

    const result = await createWorkerEngine(runner, { workerDir: '/repo/worker' }).run(request);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('timeout');
  });
});
