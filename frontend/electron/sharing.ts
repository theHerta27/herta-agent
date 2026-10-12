import { clipboard, desktopCapturer } from 'electron';
import type { ScreenshotSource } from '../shared/sharing-contracts';

export function clipboardPreview(text: string) { return { text: text.replace(/\0/g, '').slice(0, 6000), truncated: text.length > 6000 }; }
export class SharingClient {
  private controller?: AbortController;
  private known = new Map<string, { name: string; time: number }>();
  constructor(private endpoint: () => string, private token: string) {}
  clipboard = async () => clipboardPreview(await clipboard.readText());
  async sources(): Promise<ScreenshotSource[]> {
    const sources = await desktopCapturer.getSources({ types: ['window', 'screen'], thumbnailSize: { width: 0, height: 0 }, fetchWindowIcons: false });
    this.known.clear(); const result = sources.slice(0, 100).map(s => ({ id: s.id, name: s.name.slice(0, 200) }));
    for (const s of result) this.known.set(s.id, { name: s.name, time: Date.now() }); return result;
  }
  async capture(id: string) {
    const seen = this.known.get(id); if (!seen || Date.now() - seen.time > 60000) throw new Error('截图对象已变化，请重新选择。');
    const sources = await desktopCapturer.getSources({ types: [id.startsWith('window:') ? 'window' : 'screen'], thumbnailSize: { width: 1600, height: 900 }, fetchWindowIcons: false });
    const source = sources.find(s => s.id === id && s.name.slice(0, 200) === seen.name);
    if (!source || source.thumbnail.isEmpty() || source.thumbnail.toPNG().length > 4_000_000) throw new Error('截图失败或图片过大，请重试。');
    return { png: source.thumbnail.toDataURL(), name: seen.name };
  }
  cancel() { this.controller?.abort(); this.controller = undefined; }
  async ocr(png: string) {
    if (typeof png !== 'string' || !png.startsWith('data:image/png;base64,') || png.length > 5_400_000) throw new Error('invalid_image');
    const raw = png.slice('data:image/png;base64,'.length); if (!/^[A-Za-z0-9+/=]+$/.test(raw) || Buffer.from(raw, 'base64').subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') throw new Error('invalid_image');
    this.cancel(); const controller = new AbortController(); this.controller = controller;
    try { const response = await fetch(this.endpoint() + '/desktop/ocr', { method: 'POST', headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ png: raw }), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(45000)]), redirect: 'error' }); const result = await response.json(); if (!response.ok) throw new Error(result?.error?.message ?? '本机OCR识别失败。'); return result; }
    finally { if (this.controller === controller) this.controller = undefined; }
  }
}
