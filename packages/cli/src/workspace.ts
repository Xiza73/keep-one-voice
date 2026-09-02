import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Workspace } from '@kov/core';

/**
 * Temporary files live in a private directory with default `mkdtemp`
 * permissions (0700), so intermediate audio is never world readable.
 *
 * The directory is created lazily and removed by `dispose`, which must run even
 * when the pipeline fails halfway: a crashed run must not leave someone's audio
 * sitting in the system temp directory.
 */
export function createTempWorkspace(): Workspace {
  let directory: string | null = null;

  return {
    async createTempFile(suffix) {
      directory ??= await mkdtemp(join(tmpdir(), 'kov-'));
      return join(directory, `stage${suffix}`);
    },

    async remove(path) {
      // Best effort: a missing file is not a failure worth surfacing.
      await rm(path, { force: true }).catch(() => undefined);
    },

    async dispose() {
      if (directory === null) return;

      const target = directory;
      directory = null;
      await rm(target, { recursive: true, force: true }).catch(() => undefined);
    },
  };
}
