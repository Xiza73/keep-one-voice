import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

/**
 * Finding the Python worker.
 *
 * A compiled binary cannot use `import.meta.dir`: it points inside the embedded
 * filesystem, so a relative walk up to the repository resolves to nonsense like
 * `/worker`. The binary then works for `--stages decode` and nothing else.
 *
 * So the worker is looked up in the places it can actually be, in order of how
 * explicit the intent is.
 */

export interface WorkerLookup {
  readonly env: string | undefined;
  readonly execPath: string;
  readonly cwd: string;
  readonly moduleDir: string;
}

export type WorkerDir =
  | { ok: true; path: string }
  | { ok: false; searched: readonly string[]; detail: string };

export function workerDirCandidates(lookup: WorkerLookup): readonly string[] {
  const candidates = [
    // An explicit override always wins.
    lookup.env,
    // Beside the executable: how a release is laid out.
    resolve(dirname(lookup.execPath), '..', 'worker'),
    resolve(dirname(lookup.execPath), 'worker'),
    // Where the command was run from.
    resolve(lookup.cwd, 'worker'),
    // The repository, when running from source.
    resolve(lookup.moduleDir, '..', '..', '..', 'worker'),
  ].filter((path): path is string => path !== undefined);

  return [...new Set(candidates)];
}

export function resolveWorkerDir(
  candidates: readonly string[],
  exists: (path: string) => boolean = existsSync,
): WorkerDir {
  for (const path of candidates) {
    if (exists(path)) return { ok: true, path };
  }

  return {
    ok: false,
    searched: candidates,
    detail:
      `no worker directory found. Set KOV_WORKER_DIR to the ` +
      `worker/ folder of a keep-one-voice checkout. Looked in: ${candidates.join(', ')}`,
  };
}
