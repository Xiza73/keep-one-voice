import manifest from '../../../package.json';

/**
 * Read from the workspace manifest rather than written here.
 *
 * A hand-written constant drifts: the release bumps `package.json` and the
 * binary keeps reporting whatever it was born with, which costs someone an
 * afternoon working out which build they actually have.
 */
export const VERSION: string = manifest.version;
