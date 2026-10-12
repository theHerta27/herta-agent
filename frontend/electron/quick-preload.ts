import { contextBridge, ipcRenderer } from 'electron';
import type { QuickWindowBridge, QuickState } from '../shared/quick-contracts';
const bridge: QuickWindowBridge = {
  state: () => ipcRenderer.invoke('herta:quick-state'),
  onState: handler => { const listener = (_event: Electron.IpcRendererEvent, state: QuickState) => handler(state); ipcRenderer.on('herta:quick-state', listener); return () => { ipcRenderer.removeListener('herta:quick-state', listener); }; },
  input: value => ipcRenderer.invoke('herta:quick-input', value),
  close: () => ipcRenderer.invoke('herta:quick-close'),
  showMain: () => ipcRenderer.invoke('herta:quick-main'),
};
contextBridge.exposeInMainWorld('hertaQuick', bridge);
