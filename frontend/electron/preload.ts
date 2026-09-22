import { contextBridge, ipcRenderer } from 'electron';
import type { BackendStatus, DesktopBridge } from '../shared/contracts';

const bridge: DesktopBridge = {
  getBackendStatus: () => ipcRenderer.invoke('herta:backend-status'),
  onBackendStatus: handler => {
    const listener = (_event: Electron.IpcRendererEvent, status: BackendStatus) => handler(status);
    ipcRenderer.on('herta:backend-status-changed', listener);
    return () => { ipcRenderer.removeListener('herta:backend-status-changed', listener); };
  },
};
contextBridge.exposeInMainWorld('herta', bridge);
