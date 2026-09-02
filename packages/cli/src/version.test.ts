import { describe, expect, test } from 'bun:test';
import { VERSION } from './version.ts';

describe('VERSION', () => {
  test('looks like a semantic version', () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/);
  });

  test('is not the placeholder a fresh scaffold ships with', () => {
    expect(VERSION).not.toBe('0.0.0');
  });

  test('matches the workspace manifest it is released from', async () => {
    const manifest = await Bun.file(new URL('../../../package.json', import.meta.url)).json();

    expect(VERSION).toBe(manifest.version);
  });
});
