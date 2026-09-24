import { createServer } from 'vite';
import { spawn } from 'node:child_process';
import electron from 'electron';
import { buildMain, frontend } from './build.mjs';

await buildMain();
const server = await createServer({ root: frontend });
await server.listen();
const env = { ...process.env, HERTA_DESKTOP_DEV_URL: server.resolvedUrls.local[0] };
delete env.ELECTRON_RUN_AS_NODE;
// Electron is the user-facing GUI; SW_HIDE can leave its first window invisible on Windows.
const child = spawn(electron, [frontend], { cwd: frontend, env, windowsHide: false, stdio: ['ignore', 'inherit', 'inherit', 'ipc'] });
const stop = () => { if (child.connected) child.send('shutdown', () => {}); };
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
try {
  const code = await new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('close', code => resolve(code));
  });
  process.exitCode = code ?? 1;
} finally { await server.close(); }
