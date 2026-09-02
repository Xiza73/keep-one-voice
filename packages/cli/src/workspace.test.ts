import { describe, expect, test } from 'bun:test';
import { stat } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createTempWorkspace } from './workspace.ts';

const exists = async (path: string): Promise<boolean> => {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
};

describe('createTempWorkspace', () => {
  test('creates the temporary file inside a private directory', async () => {
    const workspace = createTempWorkspace();

    const path = await workspace.createTempFile('.wav');
    const mode = (await stat(dirname(path))).mode & 0o777;
    await workspace.dispose();

    expect(mode).toBe(0o700);
  });

  test('keeps the requested suffix', async () => {
    const workspace = createTempWorkspace();

    const path = await workspace.createTempFile('.wav');
    await workspace.dispose();

    expect(path).toEndWith('.wav');
  });

  test('reuses one directory across calls', async () => {
    const workspace = createTempWorkspace();

    const first = await workspace.createTempFile('.wav');
    const second = await workspace.createTempFile('.wav');
    await workspace.dispose();

    expect(dirname(first)).toBe(dirname(second));
  });

  test('removing a file that was never written is not an error', async () => {
    const workspace = createTempWorkspace();

    const path = await workspace.createTempFile('.wav');

    expect(workspace.remove(path)).resolves.toBeUndefined();
    await workspace.dispose();
  });

  test('removes a file that exists', async () => {
    const workspace = createTempWorkspace();
    const path = await workspace.createTempFile('.wav');
    await Bun.write(path, 'audio');

    await workspace.remove(path);
    const stillThere = await Bun.file(path).exists();
    await workspace.dispose();

    expect(stillThere).toBe(false);
  });

  test('dispose removes the directory it created', async () => {
    const workspace = createTempWorkspace();
    const directory = dirname(await workspace.createTempFile('.wav'));

    await workspace.dispose();

    expect(await exists(directory)).toBe(false);
  });

  test('dispose removes the directory even when files are still inside it', async () => {
    const workspace = createTempWorkspace();
    const path = await workspace.createTempFile('.wav');
    await Bun.write(path, 'audio left behind by a failed run');
    const directory = dirname(path);

    await workspace.dispose();

    expect(await exists(directory)).toBe(false);
  });

  test('dispose is safe to call when no file was ever created', async () => {
    const workspace = createTempWorkspace();

    expect(workspace.dispose()).resolves.toBeUndefined();
  });

  test('dispose is safe to call twice', async () => {
    const workspace = createTempWorkspace();
    await workspace.createTempFile('.wav');

    await workspace.dispose();

    expect(workspace.dispose()).resolves.toBeUndefined();
  });
});
