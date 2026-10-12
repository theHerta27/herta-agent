/** Keep speech below decoder limits while retaining punctuation and all text. */
export function speechChunks(text: string): string[] {
  const chunks: string[] = [];
  for (let start = 0; start < text.length;) {
    let end = Math.min(start + 120, text.length);
    if (end < text.length) {
      const part = text.slice(start, end);
      const boundary = [...part.matchAll(/[。？！!?；;\n]/g)].at(-1)?.index;
      if (boundary !== undefined && boundary >= 40) end = start + boundary + 1;
    }
    chunks.push(text.slice(start, end)); start = end;
  }
  return chunks;
}
