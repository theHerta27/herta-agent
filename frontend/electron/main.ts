import { app, BrowserWindow, ipcMain, session } from 'electron';
import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { BackendProcess } from './backend-process';

const root = resolve(__dirname, '../../..');
const data = resolve(process.env.HERTA_DESKTOP_DATA_DIR ?? join(root, '.local/desktop'));
mkdirSync(data, { recursive: true });
app.setName('Herta');
app.setPath('userData', join(data, 'electron'));

export const backend = new BackendProcess({
  root, db: join(data, 'sessions.sqlite3'),
  python: resolve(process.env.HERTA_DESKTOP_PYTHON ?? join(root, '.venv/Scripts/python.exe')),
  host: join(root, 'frontend/desktop/backend_host.py'),
});
let window: BrowserWindow | undefined;
let quitting = false;
let closing = false;

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (window?.isMinimized()) window.restore();
    window?.show();
    window?.focus();
  });
  app.on('before-quit', event => {
    if (quitting) return;
    event.preventDefault();
    if (closing) return;
    closing = true;
    void backend.stop().then(() => { quitting = true; app.quit(); }).catch(() => { closing = false; });
  });
  // Electron's Windows GUI subsystem has no reliable stdin; the dev runner uses IPC.
  if (process.send) {
    process.on('message', message => { if (message === 'shutdown') app.quit(); });
    process.on('disconnect', () => app.quit());
  }
  void app.whenReady().then(async () => {
    session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    session.defaultSession.setPermissionCheckHandler(() => false);
    window = new BrowserWindow({
      title: 'Herta', width: 1200, height: 800, minWidth: 800, minHeight: 600,
      backgroundColor: '#17181c',
      webPreferences: {
        preload: join(__dirname, 'preload.cjs'), contextIsolation: true,
        nodeIntegration: false, sandbox: true,
      },
    });
    window.setMenu(null);
    window.on('close', event => {
      if (!quitting) { event.preventDefault(); app.quit(); }
    });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', event => event.preventDefault());
    ipcMain.handle('herta:backend-status', event => {
      if (event.senderFrame !== window?.webContents.mainFrame) throw new Error('invalid_sender');
      return backend.status;
    });
    backend.subscribe(status => {
      if (window && !window.isDestroyed()) window.webContents.send('herta:backend-status-changed', status);
    });
    const devUrl = process.env.HERTA_DESKTOP_DEV_URL;
    if (devUrl) {
      const url = new URL(devUrl);
      if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1') throw new Error('invalid_dev_url');
      await window.loadURL(url.href);
    } else {
      await window.loadFile(join(__dirname, '../renderer/index.html'));
    }
    if (!closing) void backend.start();
  }).catch(() => { app.quit(); });
}
