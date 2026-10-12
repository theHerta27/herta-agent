import { app, BrowserWindow, ipcMain, session, Tray, Menu, nativeImage, globalShortcut, Notification, dialog } from 'electron';
import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { BackendProcess } from './backend-process';
import { BackendClient, readHealth } from './backend-client';
import { RunTransport } from './run-transport';
import { DesktopSettings } from './desktop-settings';
import { randomUUID, randomBytes } from 'node:crypto';
import { execFile } from 'node:child_process';
import { CompanionClient } from './companion';
import { identifier } from './backend-client';
import { WorkspaceClient } from './workspace';
import { ProductivityClient } from './productivity';
import { PersonalClient } from './personal';

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
let tray: Tray | undefined;
let dailyTimer: ReturnType<typeof setInterval> | undefined;
export const client = new BackendClient(() => {
  if (!backend.endpoint || closing) throw new Error('backend_unavailable');
  return backend.endpoint;
});
const daily = new CompanionClient(client);
const workspaceToken = randomBytes(32).toString('hex');
const workspaceClient = new WorkspaceClient(client.endpoint, workspaceToken);
const productivity = new ProductivityClient(client.endpoint, workspaceToken);
const personal = new PersonalClient(client.endpoint, workspaceToken);
let workspacePending = 0;

const settings = new DesktopSettings(join(data, 'settings.json'), { ...process.env, HERTA_WORKSPACE_TOKEN: workspaceToken }, {
  get status() { return backend.status; },
  stop: () => backend.stop(),
  configureEnvironment: env => { if (!closing) backend.configureEnvironment(env); },
  start: async () => { if (!closing) await backend.start(); },
},
  () => (transport?.activeCount ?? 0) + workspacePending,
  async () => {
    if (closing || ['starting', 'stopping'].includes(backend.status.state)) throw new Error('backend_busy');
    if (!backend.endpoint) return 0;
    const health = await readHealth(backend.endpoint);
    return health.active_runs + (health.workspace_active_jobs ?? 0);
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
    if (dailyTimer) clearInterval(dailyTimer);
    daily.cancelVoice();
    globalShortcut.unregister('CommandOrControl+Shift+H');
    tray?.destroy();
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
    session.defaultSession.setPermissionRequestHandler((contents, permission, callback, details) => callback(
      contents === window?.webContents && permission === 'media' && 'mediaTypes' in details && details.mediaTypes?.every(type => type === 'audio') === true));
    session.defaultSession.setPermissionCheckHandler((contents, permission, _origin, details) => contents === window?.webContents && permission === 'media' && details.mediaType === 'audio');
    window = new BrowserWindow({
      title: 'Herta', width: 1200, height: 800, minWidth: 800, minHeight: 600,
      backgroundColor: '#17181c',
      webPreferences: {
        preload: join(__dirname, 'preload.cjs'), contextIsolation: true,
        nodeIntegration: false, sandbox: true,
        backgroundThrottling: false, autoplayPolicy: 'no-user-gesture-required',
      },
    });
    window.setMenu(null);
    window.on('close', event => {
      if (!quitting) {
        event.preventDefault();
        window?.hide();
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
    const workspaceAction = async <T>(event: Electron.IpcMainInvokeEvent, action: () => Promise<T>) => {
      checkSender(event);
      if (settings.applying || closing) throw new Error('settings_busy');
      workspacePending++;
      try { return await action(); } finally { workspacePending--; }
    };
    ipcMain.handle('herta:workspace-roots', event => workspaceAction(event, workspaceClient.roots));
    ipcMain.handle('herta:workspace-choose', event => workspaceAction(event, async () => {
      const result = await dialog.showOpenDialog(window!, { title: '选择 Herta 可读取的目录', properties: ['openDirectory'] });
      return result.canceled || result.filePaths.length !== 1 ? null : workspaceClient.grant(result.filePaths[0]);
    }));
    ipcMain.handle('herta:workspace-share', (event, id, enabled) => workspaceAction(event, async () => {
      if (typeof enabled !== 'boolean') throw new Error('invalid_request');
      const root = (await workspaceClient.roots()).find(r => r.id === identifier(id));
      if (!root) throw new Error('目录未授权。');
      if (enabled) {
        const result = await dialog.showMessageBox(window!, { type: 'question', title: '允许聊天读取目录', message: `允许 Herta 在聊天中读取「${root.label}」？`, detail: '文件名、文本预览和分析报告可能进入聊天上下文，并发送给你配置的模型服务。敏感文件仍受保护。关闭共享只停止后续读取，已进入会话的内容仍保存在历史中。', buttons: ['取消', '允许读取'], defaultId: 0, cancelId: 0 });
        if (result.response !== 1) return root;
      }
      return workspaceClient.share(id, enabled);
    }));
    ipcMain.handle('herta:workspace-revoke', (event, id) => workspaceAction(event, () => workspaceClient.revoke(id)));
    ipcMain.handle('herta:workspace-list', (event, id, path) => workspaceAction(event, () => workspaceClient.list(id, path)));
    ipcMain.handle('herta:workspace-search', (event, id, query) => workspaceAction(event, () => workspaceClient.search(id, query)));
    ipcMain.handle('herta:workspace-read', (event, id, path) => workspaceAction(event, () => workspaceClient.read(id, path)));
    ipcMain.handle('herta:workspace-jobs', (event, id) => workspaceAction(event, () => workspaceClient.jobs(id)));
    ipcMain.handle('herta:workspace-start', (event, id, duplicates) => workspaceAction(event, () => workspaceClient.start(id, duplicates)));
    ipcMain.handle('herta:workspace-cancel', (event, id) => workspaceAction(event, () => workspaceClient.cancel(id)));
    ipcMain.handle('herta:workspace-propose', (event, id, operations) => workspaceAction(event, () => workspaceClient.propose(id, operations)));
    ipcMain.handle('herta:workspace-plans', (event, id) => workspaceAction(event, () => workspaceClient.plans(id)));
    ipcMain.handle('herta:workspace-file-jobs', (event, id) => workspaceAction(event, () => workspaceClient.fileJobs(id)));
    ipcMain.handle('herta:workspace-stop-file', (event, id) => workspaceAction(event, () => workspaceClient.stopFile(id)));
    ipcMain.handle('herta:workspace-undo', (event, id) => workspaceAction(event, () => workspaceClient.undo(id)));
    ipcMain.handle('herta:workspace-document', (event, id, path) => workspaceAction(event, () => workspaceClient.document(id, path)));
    ipcMain.handle('herta:workspace-index-documents', (event, id, paths, semantic) => workspaceAction(event, () => workspaceClient.indexDocuments(id, paths, semantic)));
    ipcMain.handle('herta:workspace-knowledge', (event, id, query, semantic) => workspaceAction(event, () => workspaceClient.knowledge(id, query, semantic)));
    ipcMain.handle('herta:workspace-transform', (event, id, request) => workspaceAction(event, () => workspaceClient.transform(id, request)));
    ipcMain.handle('herta:workspace-vault', (event, id) => workspaceAction(event, () => workspaceClient.bindVault(id)));
    ipcMain.handle('herta:workspace-document-settings', event => workspaceAction(event, () => workspaceClient.documentSettings()));
    ipcMain.handle('herta:workspace-note', (event, id, target, text) => workspaceAction(event, () => workspaceClient.note(id, target, text)));
    ipcMain.handle('herta:workspace-indexed', (event, id) => workspaceAction(event, () => workspaceClient.indexedDocuments(id)));
    ipcMain.handle('herta:workspace-forget', (event, id, path) => workspaceAction(event, () => workspaceClient.forgetDocument(id, path)));
    ipcMain.handle('herta:productivity-snapshot', event => workspaceAction(event, () => productivity.snapshot()));
    ipcMain.handle('herta:personal-snapshot', event => workspaceAction(event, () => personal.snapshot()));
    ipcMain.handle('herta:personal-action', (event, value) => workspaceAction(event, () => personal.action(value)));
    ipcMain.handle('herta:productivity-action', (event, value) => workspaceAction(event, () => productivity.action(value)));
    ipcMain.handle('herta:productivity-document', (event, id) => workspaceAction(event, () => productivity.material(id)));
    ipcMain.handle('herta:productivity-history', (event, id) => workspaceAction(event, () => productivity.history(id)));
    ipcMain.handle('herta:workspace-confirm', (event, id, digest) => workspaceAction(event, async () => {
      const plan = await workspaceClient.privatePlan(id);
      if (typeof digest !== 'string' || digest !== plan.digest || plan.conflicts.length) throw new Error('方案冲突或摘要变化，请重新预览。');
      const detail = [`目录：${plan.root_path}`, `动作数：${plan.operations.length}`, ...plan.operations.map((op, index) => `${index + 1}. ${op.kind}：${op.source ?? '(新增目录)'} → ${op.target}`), '', '逐项执行并保存收据；停止只取消未完成部分。撤销需要另行预览确认，并拒绝已被修改的文件。'].join('\n');
      const choice = await dialog.showMessageBox(window!, { type: 'question', title: plan.undo_of ? '确认撤销文件操作' : '确认文件操作', message: plan.undo_of ? '执行这份具体撤销方案？' : '执行这份具体文件方案？', detail, buttons: ['取消', '确认执行'], defaultId: 0, cancelId: 0 });
      return choice.response === 1 ? workspaceClient.confirm(id, plan.digest, randomUUID()) : null;
    }));
    ipcMain.handle('herta:daily-snapshot', event => { checkSender(event); return daily.snapshot(); });
    ipcMain.handle('herta:daily-action', (event, action) => { checkSender(event); return daily.action(action); });
    ipcMain.handle('herta:voice-status', event => { checkSender(event); return daily.voiceStatus(); });
    ipcMain.handle('herta:synthesize', (event, text) => { checkSender(event); return daily.synthesize(text); });
    ipcMain.handle('herta:transcribe', (event, wav) => { checkSender(event); return daily.transcribe(wav); });
    ipcMain.handle('herta:cancel-voice', event => { checkSender(event); return daily.cancelAndWait(); });
    const show = () => { window?.show(); if (window?.isMinimized()) window.restore(); window?.focus(); };
    const pixels = Buffer.alloc(16 * 16 * 4);
    for (let y = 1; y < 15; y++) for (let x = 1; x < 15; x++) {
      if ((x - 7.5) ** 2 + (y - 7.5) ** 2 > 49) continue;
      const h = ((x === 5 || x === 10) && y >= 4 && y <= 11) || (y === 7 && x >= 5 && x <= 10);
      pixels.set(h ? [242, 237, 255, 255] : [146, 100, 200, 255], (y * 16 + x) * 4);
    }
    tray = new Tray(nativeImage.createFromBitmap(pixels, { width: 16, height: 16 }));
    tray.setToolTip('Herta · Ctrl+Shift+H');
    tray.setContextMenu(Menu.buildFromTemplate([{ label: '打开 Herta', click: show }, { type: 'separator' }, { label: '退出 Herta', click: () => app.quit() }]));
    tray.on('double-click', show);
    globalShortcut.register('CommandOrControl+Shift+H', show);
    const attempted = new Map<string, number>();
    let polling = false;
    dailyTimer = setInterval(() => {
      if (polling || closing || !backend.endpoint) return;
      polling = true;
      void daily.snapshot().then(snapshot => {
        const hour = Number(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Shanghai' }).format(new Date()));
        const { quiet_start: start, quiet_end: end } = snapshot.preferences;
        const quiet = start === end ? false : start < end ? hour >= start && hour < end : hour >= start || hour < end;
        if (quiet || !Notification.isSupported()) return;
        for (const delivery of snapshot.deliveries) {
          if (delivery.notified || Date.now() - (attempted.get(delivery.id) ?? 0) < 60000) continue;
          attempted.set(delivery.id, Date.now());
          const notification = new Notification({ title: 'Herta 提醒', body: delivery.title });
          notification.on('click', show);
          notification.on('show', () => { void client.json(`/companion/deliveries/${identifier(delivery.id)}/notified`, 'POST', {}).catch(() => {}); });
          notification.show();
        }
      }).catch(() => {}).finally(() => { polling = false; });
    }, 1000);
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
