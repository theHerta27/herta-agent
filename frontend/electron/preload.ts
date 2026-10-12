import { contextBridge, ipcRenderer } from 'electron';
import type { BackendStatus, DesktopBridge, RunPacket } from '../shared/contracts';

const bridge: DesktopBridge = {
  sharing: {
    clipboard: () => ipcRenderer.invoke('herta:sharing-clipboard'),
    sources: () => ipcRenderer.invoke('herta:sharing-sources'),
    capture: id => ipcRenderer.invoke('herta:sharing-capture', id),
    ocr: png => ipcRenderer.invoke('herta:sharing-ocr', png),
    cancel: () => ipcRenderer.invoke('herta:sharing-cancel'),
  },
  mcp: { get: () => ipcRenderer.invoke('herta:mcp-get'), apply: value => ipcRenderer.invoke('herta:mcp-apply', value) },
  quick: {
    open: () => ipcRenderer.invoke('herta:quick-open'),
    publish: value => ipcRenderer.invoke('herta:quick-publish', value),
    onInput: handler => { const listener = (_event: Electron.IpcRendererEvent, value: Parameters<typeof handler>[0]) => handler(value); ipcRenderer.on('herta:quick-request', listener); return () => { ipcRenderer.removeListener('herta:quick-request', listener); }; },
    respond: (id, error) => ipcRenderer.invoke('herta:quick-response', id, error),
  },
  personal: {
    snapshot: () => ipcRenderer.invoke('herta:personal-snapshot'),
    action: value => ipcRenderer.invoke('herta:personal-action', value),
  },
  productivity: {
    snapshot: () => ipcRenderer.invoke('herta:productivity-snapshot'),
    action: value => ipcRenderer.invoke('herta:productivity-action', value),
    material: id => ipcRenderer.invoke('herta:productivity-document', id),
    history: id => ipcRenderer.invoke('herta:productivity-history', id),
  },
  workspace: {
    roots: () => ipcRenderer.invoke('herta:workspace-roots'),
    chooseRoot: () => ipcRenderer.invoke('herta:workspace-choose'),
    share: (id, enabled) => ipcRenderer.invoke('herta:workspace-share', id, enabled),
    revoke: id => ipcRenderer.invoke('herta:workspace-revoke', id),
    list: (id, path) => ipcRenderer.invoke('herta:workspace-list', id, path),
    search: (id, query) => ipcRenderer.invoke('herta:workspace-search', id, query),
    read: (id, path) => ipcRenderer.invoke('herta:workspace-read', id, path),
    jobs: id => ipcRenderer.invoke('herta:workspace-jobs', id),
    start: (id, duplicates) => ipcRenderer.invoke('herta:workspace-start', id, duplicates),
    cancel: id => ipcRenderer.invoke('herta:workspace-cancel', id),
    propose: (id, operations) => ipcRenderer.invoke('herta:workspace-propose', id, operations),
    plans: id => ipcRenderer.invoke('herta:workspace-plans', id),
    confirm: (id, digest) => ipcRenderer.invoke('herta:workspace-confirm', id, digest),
    fileJobs: id => ipcRenderer.invoke('herta:workspace-file-jobs', id),
    stopFile: id => ipcRenderer.invoke('herta:workspace-stop-file', id),
    undo: id => ipcRenderer.invoke('herta:workspace-undo', id),
    document: (id, path) => ipcRenderer.invoke('herta:workspace-document', id, path),
    indexDocuments: (id, paths, semantic) => ipcRenderer.invoke('herta:workspace-index-documents', id, paths, semantic),
    knowledge: (id, query, semantic) => ipcRenderer.invoke('herta:workspace-knowledge', id, query, semantic),
    transform: (id, request) => ipcRenderer.invoke('herta:workspace-transform', id, request),
    bindVault: id => ipcRenderer.invoke('herta:workspace-vault', id),
    documentSettings: () => ipcRenderer.invoke('herta:workspace-document-settings'),
    note: (id, target, text) => ipcRenderer.invoke('herta:workspace-note', id, target, text),
    indexedDocuments: id => ipcRenderer.invoke('herta:workspace-indexed', id),
    forgetDocument: (id, path) => ipcRenderer.invoke('herta:workspace-forget', id, path),
  },
  companion: {
    snapshot: () => ipcRenderer.invoke('herta:daily-snapshot'),
    action: action => ipcRenderer.invoke('herta:daily-action', action),
    voiceStatus: () => ipcRenderer.invoke('herta:voice-status'),
    synthesize: text => ipcRenderer.invoke('herta:synthesize', text),
    transcribe: wav => ipcRenderer.invoke('herta:transcribe', wav),
    cancelVoice: () => ipcRenderer.invoke('herta:cancel-voice'),
  },
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
