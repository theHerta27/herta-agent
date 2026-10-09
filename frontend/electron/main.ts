import { app, BrowserWindow, dialog, ipcMain, session } from 'electron';
import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { BackendProcess } from './backend-process';
import { BackendClient, readHealth } from './backend-client';
import { RunTransport } from './run-transport';
import { DesktopSettings } from './desktop-settings';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';

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
let transport: RunTransport | undefined;
export const client = new BackendClient(() => {
  if (!backend.endpoint || closing) throw new Error('backend_unavailable');
  return backend.endpoint;
});

const settings = new DesktopSettings(join(data, 'settings.json'), process.env, {
  get status() { return backend.status; },
  stop: () => backend.stop(),
  configureEnvironment: env => { if (!closing) backend.configureEnvironment(env); },
  start: async () => { if (!closing) await backend.start(); },
},
  () => transport?.activeCount ?? 0,
  async () => {
    if (closing || ['starting', 'stopping'].includes(backend.status.state)) throw new Error('backend_busy');
    if (!backend.endpoint) return 0;
    return (await readHealth(backend.endpoint)).active_runs;
  });
backend.configureEnvironment(settings.environment());

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
    // stop() normally finishes within 20s + 5s tree kill + 5s pipe drain.
    // A rejected/stalled shutdown must not retain this process's instance lock.
    let forcing = false;
    const forceExit = () => {
      if (forcing) return;
      forcing = true;
      clearTimeout(watchdog);
      execFile(join(process.env.SystemRoot ?? 'C:\\Windows', 'System32/taskkill.exe'),
        ['/PID', String(process.pid), '/T', '/F'], { windowsHide: true, timeout: 5000 },
        () => app.exit(1));
    };
    const watchdog = setTimeout(forceExit, 35000);
    transport?.dispose();
    void backend.stop().then(() => {
      clearTimeout(watchdog);
      quitting = true;
      app.quit();
    }).catch(forceExit);
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
      if (!quitting) {
        event.preventDefault();
        if (transport?.activeCount && dialog.showMessageBoxSync(window!, { type: 'question', message: '取消运行并退出？', buttons: ['取消运行并退出', '返回'], defaultId: 1, cancelId: 1 }) !== 0) return;
        app.quit();
      }
    });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', event => event.preventDefault());
    ipcMain.handle('herta:backend-status', event => {
      if (event.senderFrame !== window?.webContents.mainFrame) throw new Error('invalid_sender');
      return backend.status;
    });
    const checkSender = (event: Electron.IpcMainInvokeEvent) => {
      if (event.senderFrame !== window?.webContents.mainFrame) throw new Error('invalid_sender');
    };
    let subscribed = false;
    const acknowledgements = new Map<string, () => void>();
    transport = new RunTransport(client, packet => new Promise((resolve, reject) => {
      if (!subscribed || !window || window.isDestroyed()) { reject(new Error('renderer_unavailable')); return; }
      const batchId = randomUUID();
      const timer = setTimeout(() => { acknowledgements.delete(batchId); reject(new Error('renderer_slow')); }, 2000);
      acknowledgements.set(batchId, () => { clearTimeout(timer); acknowledgements.delete(batchId); resolve(); });
      window.webContents.send('herta:run-events', packet, batchId);
    }));
    ipcMain.on('herta:subscribe-runs', event => { if (event.senderFrame === window?.webContents.mainFrame) subscribed = true; });
    ipcMain.on('herta:run-ack', (event, batchId) => { if (event.senderFrame === window?.webContents.mainFrame) acknowledgements.get(batchId)?.(); });
    ipcMain.handle('herta:start-run', (event, request) => { checkSender(event); if (settings.applying || closing) throw new Error('settings_busy'); if (!subscribed) throw new Error('renderer_unavailable'); transport!.start(request); });
    ipcMain.handle('herta:cancel-request', (event, id) => { checkSender(event); return transport!.cancel(id); });
    const dropStreams = () => { subscribed = false; transport?.dispose(); };
    window.webContents.on('render-process-gone', dropStreams);
    window.webContents.on('did-start-navigation', (_event, _url, inPlace, mainFrame) => { if (mainFrame && !inPlace) dropStreams(); });
    ipcMain.handle('herta:list-sessions', (event, after, limit) => { checkSender(event); return client.listSessions(after, limit); });
    ipcMain.handle('herta:create-session', event => { checkSender(event); return client.createSession(); });
    ipcMain.handle('herta:get-session', (event, id, after, limit) => { checkSender(event); return client.getSession(id, after, limit); });
    ipcMain.handle('herta:get-settings', event => { checkSender(event); return settings.get(); });
    ipcMain.handle('herta:apply-settings', (event, value) => { checkSender(event); return settings.apply(value); });
    ipcMain.handle('herta:get-run-diagnostics', (event, id) => { checkSender(event); return client.getRunDiagnostics(id); });
    ipcMain.handle('herta:get-run', (event, id) => { checkSender(event); return client.getRun(id); });
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
