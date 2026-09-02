import { describe, expect, test } from 'bun:test';
import { resolveWorkerDir, workerDirCandidates } from './workerdir.ts';

const LOOKUP = {
  env: undefined,
  execPath: '/opt/kov/bin/kov',
  cwd: '/home/someone/project',
  moduleDir: '/repo/packages/cli/src',
};

describe('workerDirCandidates', () => {
  test('puts an explicit override first', () => {
    const candidates = workerDirCandidates({ ...LOOKUP, env: '/custom/worker' });

    expect(candidates[0]).toBe('/custom/worker');
  });

  test('looks beside the executable, which is how a release is laid out', () => {
    expect(workerDirCandidates(LOOKUP)).toContain('/opt/kov/worker');
  });

  test('looks in the working directory', () => {
    expect(workerDirCandidates(LOOKUP)).toContain('/home/someone/project/worker');
  });

  test('looks in the repository when running from source', () => {
    expect(workerDirCandidates(LOOKUP)).toContain('/repo/worker');
  });

  test('never repeats a location', () => {
    const candidates = workerDirCandidates({
      ...LOOKUP,
      execPath: '/repo/bin/kov',
      cwd: '/repo',
    });

    expect(new Set(candidates).size).toBe(candidates.length);
  });
});

describe('resolveWorkerDir', () => {
  test('returns the first location that exists', () => {
    const found = resolveWorkerDir(['/a/worker', '/b/worker'], (path) => path === '/b/worker');

    expect(found).toEqual({ ok: true, path: '/b/worker' });
  });

  test('prefers an earlier location when both exist', () => {
    const found = resolveWorkerDir(['/a/worker', '/b/worker'], () => true);

    expect(found).toEqual({ ok: true, path: '/a/worker' });
  });

  test('reports every place it looked when nothing is there', () => {
    const found = resolveWorkerDir(['/a/worker', '/b/worker'], () => false);

    expect(found.ok).toBe(false);
    if (!found.ok) expect(found.searched).toEqual(['/a/worker', '/b/worker']);
  });

  test('names the override so the message is actionable', () => {
    const found = resolveWorkerDir(['/a/worker'], () => false);

    expect(found.ok).toBe(false);
    if (!found.ok) expect(found.detail).toContain('KOV_WORKER_DIR');
  });

  test('lists the places it looked in the message', () => {
    const found = resolveWorkerDir(['/a/worker'], () => false);

    expect(found.ok).toBe(false);
    if (!found.ok) expect(found.detail).toContain('/a/worker');
  });
});
