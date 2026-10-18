// Production build: one SPA shell, split route chunks, base path and API URL baked in, 404.html for Pages.
import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildSite } from '../build.ts';

let out = '';
let files: string[] = [];
const read = (file: string) => readFile(join(out, file), 'utf8');

beforeAll(async () => {
  out = await mkdtemp(join(tmpdir(), 'harbor-site-'));
  await buildSite({ outdir: out, basePath: '/harbor', apiUrl: 'https://api.example.org' });
  files = await readdir(out);
}, 60_000); // a full production build
afterAll(() => rm(out, { recursive: true, force: true }));

describe('build', () => {
  test('emits the shell and a GitHub Pages fallback', async () => {
    expect(files).toContain('index.html');
    expect(await read('404.html')).toBe(await read('index.html'));
  });

  test('asset URLs live under the base path', async () => {
    const html = await read('index.html');
    const urls = [...html.matchAll(/(?:href|src)="([^"]+)"/g)].map((m) => m[1]);
    expect(urls.length).toBeGreaterThan(2);
    for (const url of urls) expect(url).toStartWith('/harbor/');
  });

  test('routes are split into separate chunks', () => {
    expect(files.filter((f) => f.endsWith('.js')).length).toBeGreaterThan(5);
  });

  test('the base path and API URL are baked in', async () => {
    const js = (await Promise.all(files.filter((f) => f.endsWith('.js')).map(read))).join('\n');
    expect(js).toContain('https://api.example.org');
    expect(js).toContain('"/harbor"');
  });
});
