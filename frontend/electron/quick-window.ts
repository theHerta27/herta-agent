import { BrowserWindow, ipcMain } from 'electron';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import type { QuickInput, QuickState } from '../shared/quick-contracts';

export class QuickWindow {
  private window?: BrowserWindow;
  private current: QuickState | null = null;
  private pending = new Map<string, { resolve: () => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  constructor(private main: BrowserWindow, private directory: string, private devUrl?: string) {
    const isMain = (event: Electron.IpcMainInvokeEvent) => { if (event.senderFrame !== this.main.webContents.mainFrame) throw new Error('invalid_sender'); };
    const isQuick = (event: Electron.IpcMainInvokeEvent) => { if (!this.window || event.senderFrame !== this.window.webContents.mainFrame) throw new Error('invalid_sender'); };
    ipcMain.handle('herta:quick-open', event => { isMain(event); return this.open(); });
    ipcMain.handle('herta:quick-publish', (event, value: QuickState) => { isMain(event); if (!value || typeof value.draft !== 'string' || value.draft.length > 10000 || typeof value.lastReply !== 'string' || value.lastReply.length > 1200) throw new Error('invalid_request'); this.current = { ...value }; if (this.window && !this.window.isDestroyed()) this.window.webContents.send('herta:quick-state', this.current); });
    ipcMain.handle('herta:quick-state', event => { isQuick(event); return this.current; });
    ipcMain.handle('herta:quick-input', (event, value: QuickInput) => {
      isQuick(event);
      if (!value || !['draft', 'send'].includes(value.kind) || typeof value.text !== 'string' || value.text.length > 10000 || typeof value.expectedDraft !== 'string' || value.expectedDraft.length > 10000 || (value.sessionId !== null && (typeof value.sessionId !== 'string' || value.sessionId.length > 64))) throw new Error('invalid_request');
      if (this.pending.size || !this.current) throw new Error('主窗口正在处理，请稍后重试。');
      const id = randomUUID();
      return new Promise<void>((resolve, reject) => { const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('主窗口响应超时，请检查当前会话。')); }, 10000); this.pending.set(id, { resolve, reject, timer }); this.main.webContents.send('herta:quick-request', { id, input: value }); });
    });
    ipcMain.handle('herta:quick-response', (event, id: string, error?: string) => { isMain(event); const pending = this.pending.get(id); if (!pending) return; clearTimeout(pending.timer); this.pending.delete(id); if (error) pending.reject(new Error(String(error).slice(0, 500))); else pending.resolve(); });
    ipcMain.handle('herta:quick-close', event => { isQuick(event); this.window?.hide(); });
    ipcMain.handle('herta:quick-main', event => { isQuick(event); this.main.show(); this.main.focus(); });
  }
  async open() {
    if (!this.window || this.window.isDestroyed()) {
      this.window = new BrowserWindow({ title: 'Herta · 快捷面板', width: 500, height: 450, minWidth: 420, minHeight: 360, show: false, backgroundColor: '#17181c', webPreferences: { preload: join(this.directory, 'quick-preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false } });
      this.window.setMenu(null); this.window.webContents.setWindowOpenHandler(() => ({ action: 'deny' })); this.window.webContents.on('will-navigate', event => event.preventDefault());
      this.window.on('close', event => { event.preventDefault(); this.window?.hide(); });
      if (this.devUrl) { const url = new URL(this.devUrl); url.searchParams.set('quick', '1'); await this.window.loadURL(url.href); }
      else await this.window.loadFile(join(this.directory, '../renderer/index.html'), { query: { quick: '1' } });
    }
    this.window.show(); this.window.focus();
  }
  dispose() { for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(new Error('desktop_closed')); } this.pending.clear(); this.window?.destroy(); }
}
