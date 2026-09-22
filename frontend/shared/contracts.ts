export type BackendStatus = {
  state: 'starting' | 'ready' | 'needs_configuration' | 'unavailable' | 'stopping' | 'stopped';
  reason?: 'start_failed' | 'process_exited' | 'stop_failed';
};

export interface DesktopBridge {
  getBackendStatus(): Promise<BackendStatus>;
  onBackendStatus(handler: (status: BackendStatus) => void): () => void;
}

declare global { interface Window { herta: DesktopBridge } }
