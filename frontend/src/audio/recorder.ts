export function pcmWav(chunks: Float32Array[], rate: number): Uint8Array {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  if (!Number.isFinite(rate) || rate < 16000 || length <= 0 || length / rate > 60) throw new Error('recording_limit');
  const input = new Float32Array(length); let offset = 0;
  for (const chunk of chunks) { input.set(chunk, offset); offset += chunk.length; }
  const frames = Math.floor(length * 16000 / rate);
  const result = new Uint8Array(44 + frames * 2); const data = new DataView(result.buffer);
  const text = (position: number, value: string) => { for (let i = 0; i < value.length; i++) data.setUint8(position + i, value.charCodeAt(i)); };
  text(0, 'RIFF'); data.setUint32(4, result.length - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
  data.setUint32(16, 16, true); data.setUint16(20, 1, true); data.setUint16(22, 1, true);
  data.setUint32(24, 16000, true); data.setUint32(28, 32000, true); data.setUint16(32, 2, true); data.setUint16(34, 16, true);
  text(36, 'data'); data.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i++) {
    const position = i * rate / 16000; const base = Math.floor(position); const fraction = position - base;
    const value = Math.max(-1, Math.min(1, input[base] * (1 - fraction) + (input[base + 1] ?? input[base]) * fraction));
    data.setInt16(44 + i * 2, Math.trunc(value * (value < 0 ? 32768 : 32767)), true);
  }
  return result;
}

export class Recorder {
  private generation = 0;
  private stream?: MediaStream;
  private context?: AudioContext;
  private processor?: ScriptProcessorNode;
  private source?: MediaStreamAudioSourceNode;
  private chunks: Float32Array[] = [];
  private timer?: ReturnType<typeof setTimeout>;
  async start(onLimit: () => void): Promise<boolean> {
    const generation = ++this.generation;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
    if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); return false; }
    this.stream = stream; this.context = new AudioContext(); this.chunks = [];
    this.source = this.context.createMediaStreamSource(stream);
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = event => {
      if (!this.context) return;
      const frames = this.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const remaining = Math.floor(this.context.sampleRate * 60) - frames;
      if (remaining > 0) this.chunks.push(event.inputBuffer.getChannelData(0).slice(0, remaining));
    };
    const muted = this.context.createGain(); muted.gain.value = 0;
    this.source.connect(this.processor); this.processor.connect(muted); muted.connect(this.context.destination);
    this.timer = setTimeout(onLimit, 60000); await this.context.resume(); return true;
  }
  async stop(): Promise<Uint8Array> {
    const rate = this.context?.sampleRate ?? 16000;
    const chunks = this.chunks; await this.cancel();
    return pcmWav(chunks, rate);
  }
  async cancel() {
    ++this.generation; if (this.timer) clearTimeout(this.timer);
    this.processor?.disconnect(); this.source?.disconnect();
    this.stream?.getTracks().forEach(track => track.stop());
    const context = this.context; this.context = undefined; this.stream = undefined; this.chunks = [];
    if (context && context.state !== 'closed') await context.close();
  }
}
