import type { ServiceEvent } from '../../shared/contracts';
export class SSEParser {
  private decoder = new TextDecoder('utf-8', { fatal: true });
  private buffer = '';
  private data: string[] = [];
  push(bytes: Uint8Array): ServiceEvent[] {
    this.buffer += this.decoder.decode(bytes, { stream: true });
    if (this.buffer.length + this.data.join('').length > 512 * 1024) throw new Error('frame_too_large');
    const events: ServiceEvent[] = [];
    while (true) {
      const index = this.buffer.search(/[\r\n]/);
      if (index < 0 || (this.buffer[index] === '\r' && index === this.buffer.length - 1)) break;
      const line = this.buffer.slice(0, index);
      const length = this.buffer.slice(index, index + 2) === '\r\n' ? 2 : 1;
      this.buffer = this.buffer.slice(index + length);
      if (line.startsWith('data:')) this.data.push(line.slice(5).replace(/^ /, ''));
      if (line === '' && this.data.length) {
        const value = JSON.parse(this.data.join('\n'));
        this.data = [];
        if (value.schema_version !== 1 || !Number.isInteger(value.seq) || value.seq < 1
          || typeof value.type !== 'string' || typeof value.run_id !== 'string'
          || typeof value.session_id !== 'string' || !value.payload || typeof value.payload !== 'object') throw new Error('invalid_event');
        events.push(value);
      }
    }
    return events;
  }
}
