export interface ScreenshotSource { id: string; name: string }
export interface SharingBridge {
  clipboard(): Promise<{ text: string; truncated: boolean }>;
  sources(): Promise<ScreenshotSource[]>;
  capture(id: string): Promise<{ png: string; name: string }>;
  ocr(png: string): Promise<{ text: string; truncated: boolean; engine: string; language: string }>;
  cancel(): Promise<void>;
}
export interface MCPServer { name: string; command: string; args: string[]; allowed_tools: string[]; timeout: number }
export interface MCPConfiguration { servers: MCPServer[] }
export interface MCPBridge { get(): Promise<MCPConfiguration>; apply(value: MCPConfiguration): Promise<{ saved: boolean; available: boolean }> }
