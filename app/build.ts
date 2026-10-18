// Builds the React app into dist/. The Python server serves it at /; GitHub Pages serves it under /<repo>/.
//   HARBOR_BASE_PATH  path the site lives under, e.g. /harbor on Pages (default: /)
//   HARBOR_API_URL    a deployed Harbor server for static hosting (default: same origin)
import { copyFile, readFile, rm, writeFile } from 'node:fs/promises';

interface BuildOptions {
  outdir: string;
  basePath?: string;
  apiUrl?: string;
}

export async function buildSite({ outdir, basePath = '', apiUrl = '' }: BuildOptions) {
  const base = basePath.replace(/\/$/, '');
  await rm(outdir, { recursive: true, force: true });
  const result = await Bun.build({
    entrypoints: [`${import.meta.dir}/index.html`],
    outdir,
    minify: true,
    splitting: true, // each lazy route becomes its own chunk
    publicPath: `${base}/`,
    define: {
      HARBOR_API_URL: JSON.stringify(apiUrl),
      HARBOR_BASE_PATH: JSON.stringify(base),
      'process.env.NODE_ENV': '"production"',
    },
  });
  if (!result.success) throw new AggregateError(result.logs, 'Build failed');
  await addManifest(outdir, base);
  // GitHub Pages serves 404.html for unknown paths: let the router handle deep links.
  await copyFile(`${outdir}/index.html`, `${outdir}/404.html`);
  return result.outputs;
}

/** Web app manifest, so "Add to Home Screen" opens the app full screen. */
async function addManifest(outdir: string, base: string) {
  await copyFile(`${import.meta.dir}/src/assets/icon-512.png`, `${outdir}/icon-512.png`);
  const manifest = {
    name: 'Harbor',
    short_name: 'Harbor',
    start_url: `${base}/app`,
    scope: `${base}/`,
    display: 'standalone',
    background_color: '#f8f9f6',
    theme_color: '#f8f9f6',
    icons: [{ src: `${base}/icon-512.png`, sizes: '512x512', type: 'image/png', purpose: 'any maskable' }],
  };
  await writeFile(`${outdir}/manifest.webmanifest`, JSON.stringify(manifest));
  const index = `${outdir}/index.html`;
  const html = await readFile(index, 'utf8');
  await writeFile(index, html.replace('</head>', `<link rel="manifest" href="${base}/manifest.webmanifest"></head>`));
}

if (import.meta.main) {
  const outputs = await buildSite({
    outdir: `${import.meta.dir}/dist`,
    basePath: process.env.HARBOR_BASE_PATH,
    apiUrl: process.env.HARBOR_API_URL,
  });
  console.log(`Built ${outputs.length} files into app/dist`);
}
