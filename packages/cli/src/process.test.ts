import { describe, expect, test } from 'bun:test';
import { spawnRunner } from './process.ts';

describe('spawnRunner', () => {
  test('captures stdout and the exit code of a successful command', async () => {
    const outcome = await spawnRunner.run({ command: 'echo', args: ['hello'] });

    expect(outcome.kind).toBe('exited');
    if (outcome.kind === 'exited') {
      expect(outcome.code).toBe(0);
      expect(outcome.stdout.trim()).toBe('hello');
    }
  });

  test('captures stderr and a non-zero exit code', async () => {
    const outcome = await spawnRunner.run({
      command: 'sh',
      args: ['-c', 'echo boom >&2; exit 3'],
    });

    expect(outcome.kind).toBe('exited');
    if (outcome.kind === 'exited') {
      expect(outcome.code).toBe(3);
      expect(outcome.stderr.trim()).toBe('boom');
    }
  });

  test('reports not-found instead of throwing when the binary does not exist', async () => {
    const outcome = await spawnRunner.run({
      command: 'kov-binary-that-does-not-exist',
      args: [],
    });

    expect(outcome.kind).toBe('not-found');
  });

  test('writes stdin to the child process', async () => {
    const outcome = await spawnRunner.run({ command: 'cat', args: [], stdin: 'piped input' });

    expect(outcome.kind).toBe('exited');
    if (outcome.kind === 'exited') expect(outcome.stdout).toBe('piped input');
  });

  test('does not run the arguments through a shell', async () => {
    const outcome = await spawnRunner.run({ command: 'echo', args: ['$HOME; rm -rf /'] });

    expect(outcome.kind).toBe('exited');
    if (outcome.kind === 'exited') expect(outcome.stdout.trim()).toBe('$HOME; rm -rf /');
  });

  test('reports a timeout and does not hang on a long running command', async () => {
    const outcome = await spawnRunner.run({
      command: 'sh',
      args: ['-c', 'sleep 5'],
      timeoutMs: 150,
    });

    expect(outcome.kind).toBe('timeout');
  });
});
