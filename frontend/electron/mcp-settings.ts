import { existsSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { isAbsolute } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { MCPConfiguration } from '../shared/sharing-contracts';
import type { BackendStatus } from '../shared/contracts';

export function validateMCPConfig(input: unknown): MCPConfiguration {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(k => k !== 'servers')) throw new Error('invalid_mcp_config');
  const servers = (input as MCPConfiguration).servers;
  if (!Array.isArray(servers) || servers.length > 3 || JSON.stringify(input).length > 32000) throw new Error('invalid_mcp_config');
  const names = new Set<string>();
  for (const server of servers) {
    if (!server || typeof server !== 'object' || Object.keys(server).some(k => !['name', 'command', 'args', 'allowed_tools', 'timeout'].includes(k)) || typeof server.name !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(server.name) || names.has(server.name) || typeof server.command !== 'string' || !isAbsolute(server.command) || !existsSync(server.command) || !statSync(server.command).isFile() || !Array.isArray(server.args) || server.args.length > 32 || server.args.some(s => typeof s !== 'string' || s.length > 1000 || s.includes('\0')) || !Array.isArray(server.allowed_tools) || !server.allowed_tools.length || server.allowed_tools.length > 64 || new Set(server.allowed_tools).size !== server.allowed_tools.length || server.allowed_tools.some(s => typeof s !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(s)) || typeof server.timeout !== 'number' || !Number.isFinite(server.timeout) || server.timeout <= 0 || server.timeout > 600) throw new Error('invalid_mcp_config');
    names.add(server.name);
  }
  return structuredClone({ servers });
}
export function configureMCPEnvironment(file: string, env: NodeJS.ProcessEnv) {
  if (!existsSync(file)) return;
  try { const saved = JSON.parse(readFileSync(file, 'utf8')); if (Object.keys(saved).length === 1 && Array.isArray(saved.servers) && saved.servers.length === 0) { delete env.HERTA_MCP_CONFIG; return; } } catch { /* The backend reports invalid active config safely. */ }
  env.HERTA_MCP_CONFIG = file;
}
export class MCPSettings {
  applying = false;
  constructor(private file: string, private env: NodeJS.ProcessEnv, private restart: () => Promise<BackendStatus>, private confirm: (config: MCPConfiguration) => Promise<boolean>, private preflight: () => Promise<void> = async () => {}) {}
  get(): MCPConfiguration { if (!existsSync(this.file)) return { servers: [] }; return validateMCPConfig(JSON.parse(readFileSync(this.file, 'utf8'))); }
  async apply(input: unknown) {
    const value = validateMCPConfig(input); if (this.applying) throw new Error('settings_busy');
    this.applying = true; const old = this.env.HERTA_MCP_CONFIG; const candidate = this.file + '.' + randomUUID() + '.candidate'; let changed = false;
    try {
      await this.preflight();
      if (value.servers.length && !await this.confirm(value)) return { saved: false, available: false };
      if (value.servers.length) { writeFileSync(candidate, JSON.stringify(value), { mode: 0o600, flag: 'wx' }); this.env.HERTA_MCP_CONFIG = candidate; }
      else delete this.env.HERTA_MCP_CONFIG;
      changed = true; const status = await this.restart(); if (status.mcpError) throw new Error('MCP服务发现失败或白名单工具非只读。');
      if (value.servers.length) { renameSync(candidate, this.file); this.env.HERTA_MCP_CONFIG = this.file; }
      else writeFileSync(this.file, JSON.stringify({ servers: [] }), { mode: 0o600 });
      return { saved: true, available: !!status.mcpAvailable };
    } catch (error) {
      if (old === undefined) delete this.env.HERTA_MCP_CONFIG; else this.env.HERTA_MCP_CONFIG = old;
      if (changed) { try { await this.restart(); } catch { throw new Error('MCP恢复失败，请重启Herta并检查扩展配置。'); } throw new Error('MCP连接或保存失败，已恢复先前配置。'); }
      throw error;
    } finally { if (existsSync(candidate)) unlinkSync(candidate); this.applying = false; }
  }
}
