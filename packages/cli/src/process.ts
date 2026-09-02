/**
 * Process spawning boundary.
 *
 * Everything that leaves this process goes through here, so there is a single
 * place to audit. Arguments are always an array — never a shell string — so a
 * file name can never be reinterpreted as a command.
 */

export interface ProcessSpec {
  readonly command: string;
  readonly args: readonly string[];
  readonly stdin?: string;
  readonly timeoutMs?: number;
  readonly cwd?: string;
}

export type ProcessOutcome =
  | { kind: 'exited'; code: number; stdout: string; stderr: string }
  | { kind: 'not-found' }
  | { kind: 'timeout' };

export interface ProcessRunner {
  run(spec: ProcessSpec): Promise<ProcessOutcome>;
}

export const spawnRunner: ProcessRunner = {
  async run(spec) {
    const spawn = () =>
      Bun.spawn([spec.command, ...spec.args], {
        stdin: spec.stdin === undefined ? 'ignore' : new TextEncoder().encode(spec.stdin),
        stdout: 'pipe',
        stderr: 'pipe',
        cwd: spec.cwd,
      });

    let child: ReturnType<typeof spawn>;

    try {
      child = spawn();
    } catch {
      // Bun throws synchronously when the executable is not on PATH.
      return { kind: 'not-found' };
    }

    let timedOut = false;
    const timer =
      spec.timeoutMs === undefined
        ? undefined
        : setTimeout(() => {
            timedOut = true;
            child.kill('SIGKILL');
          }, spec.timeoutMs);

    try {
      const [stdout, stderr, code] = await Promise.all([
        new Response(child.stdout).text(),
        new Response(child.stderr).text(),
        child.exited,
      ]);

      if (timedOut) return { kind: 'timeout' };

      return { kind: 'exited', code: code ?? -1, stdout, stderr };
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  },
};
