import { contextBridge, ipcRenderer } from 'electron';
import type { BackendStatus, DesktopBridge, RunPacket } from '../shared/contracts';

const bridge: DesktopBridge = {
  getSettings: () => ipcRenderer.invoke('herta:get-settings'),
  applySettings: settings => ipcRenderer.invoke('herta:apply-settings', settings),
  getRunDiagnostics: id => ipcRenderer.invoke('herta:get-run-diagnostics', id),
  getBackendStatus: () => ipcRenderer.invoke('herta:backend-status'),
  listSessions: (after, limit) => ipcRenderer.invoke('herta:list-sessions', after, limit),
  createSession: () => ipcRenderer.invoke('herta:create-session'),
  getSession: (id, after, limit) => ipcRenderer.invoke('herta:get-session', id, after, limit),
  getRun: id => ipcRenderer.invoke('herta:get-run', id),
  startRun: request => ipcRenderer.invoke('herta:start-run', request),
  cancelRequest: id => ipcRenderer.invoke('herta:cancel-request', id),
  onRunEvents: handler => {
    const listener = (_event: Electron.IpcRendererEvent, packet: RunPacket, batchId: string) => {
      try { handler(packet); } finally { ipcRenderer.send('herta:run-ack', batchId); }
    };
    ipcRenderer.on('herta:run-events', listener);
    ipcRenderer.send('herta:subscribe-runs');
    return () => { ipcRenderer.removeListener('herta:run-events', listener); };
  },
  onBackendStatus: handler => {
    const listener = (_event: Electron.IpcRendererEvent, status: BackendStatus) => handler(status);
    ipcRenderer.on('herta:backend-status-changed', listener);
    return () => { ipcRenderer.removeListener('herta:backend-status-changed', listener); };
  },
};
contextBridge.exposeInMainWorld('herta', bridge);
