export interface Health {
  storage_writable: boolean;
  chat_available: boolean;
  rag_available: boolean;
  active_runs: number;
}

export async function readHealth(endpoint: string): Promise<Health> {
  const response = await fetch(endpoint + '/health', { signal: AbortSignal.timeout(3000), redirect: 'error' });
  if (!response.ok) throw new Error('health_failed');
  const value = await response.json();
  if (typeof value.storage_writable !== 'boolean' || typeof value.chat_available !== 'boolean'
    || typeof value.rag_available !== 'boolean' || !Number.isInteger(value.active_runs)) {
    throw new Error('health_invalid');
  }
  return value;
}
