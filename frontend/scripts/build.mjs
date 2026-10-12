import { build } from 'esbuild';
import { build as buildRenderer } from 'vite';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

export const frontend = fileURLToPath(new URL('..', import.meta.url));
export async function buildMain() {
  await build({
    absWorkingDir: frontend, entryPoints: ['electron/main.ts', 'electron/preload.ts', 'electron/quick-preload.ts'],
    bundle: true, platform: 'node', format: 'cjs', target: 'node22',
    external: ['electron'], outdir: 'dist/electron', outExtension: { '.js': '.cjs' },
  });
}
if (resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildRenderer({ root: frontend });
  await buildMain();
}
