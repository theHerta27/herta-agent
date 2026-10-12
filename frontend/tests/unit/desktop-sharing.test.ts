import { expect, it, vi } from 'vitest';
import { SharingClient } from '../../electron/sharing';
import { configureMCPEnvironment, MCPSettings, validateMCPConfig } from '../../electron/mcp-settings';
import { resolve } from 'node:path';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

it('OCR only posts validated PNG bytes to the fixed private endpoint', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ text: 'fixture' }) }); vi.stubGlobal('fetch', fetcher);
  const share = new SharingClient(() => 'http://127.0.0.1:123', 'private');
  await expect(share.ocr('https://arbitrary')).rejects.toThrow();
  await share.ocr('data:image/png;base64,iVBORw0KGgo=');
  expect(fetcher.mock.calls[0][0]).toBe('http://127.0.0.1:123/desktop/ocr');
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer private'); vi.unstubAllGlobals();
});
it('disabling MCP persists across reopen even when an older external environment config exists', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'herta-mcp-disabled-'));
  try {
    const file = join(folder, 'mcp.json'); const env: NodeJS.ProcessEnv = { HERTA_MCP_CONFIG: 'external.json' };
    const settings = new MCPSettings(file, env, async () => ({ state: 'ready' }), async () => true);
    await settings.apply({ servers: [] });
    const reopened: NodeJS.ProcessEnv = { HERTA_MCP_CONFIG: 'external.json' };
    configureMCPEnvironment(file, reopened);
    expect(reopened.HERTA_MCP_CONFIG).toBeUndefined();
  } finally { await rm(folder, { recursive: true, force: true }); }
});
it('MCP confirmation owns the apply lock so concurrent requests cannot also prompt', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'herta-mcp-'));
  try {
    let decide!: (ok: boolean) => void;
    const confirm = vi.fn(() => new Promise<boolean>(resolve => { decide = resolve; }));
    const settings = new MCPSettings(join(folder, 'mcp.json'), {}, async () => ({ state: 'ready' }), confirm);
    const input = { servers: [{ name: 'local', command: process.execPath, args: [], allowed_tools: ['read_status'], timeout: 10 }] };
    const first = settings.apply(input);
    const second = settings.apply(input);
    await expect(second).rejects.toThrow(); expect(confirm).toHaveBeenCalledTimes(1);
    decide(false); await first;
  } finally { await rm(folder, { recursive: true, force: true }); }
});
it('MCP config requires existing executables, unique servers and explicit allowlists', () => {
  const good = { servers: [{ name: 'local', command: resolve(process.execPath), args: [], allowed_tools: ['read_status'], timeout: 10 }] };
  expect(validateMCPConfig(good).servers).toHaveLength(1);
  expect(() => validateMCPConfig({ servers: [{ ...good.servers[0], command: 'node' }] })).toThrow();
  expect(() => validateMCPConfig({ servers: [...good.servers, ...good.servers] })).toThrow();
  expect(() => validateMCPConfig({ servers: [{ ...good.servers[0], env: { SECRET: 'ignored' } }] })).toThrow();
});
