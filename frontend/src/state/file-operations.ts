import type { FileOperation } from '../../shared/workspace-contracts';

const categories: Record<string, string[]> = {
  文档: ['md', 'txt', 'pdf', 'docx', 'doc', 'pptx', 'xlsx', 'csv'],
  图片: ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'],
  音频资料: ['wav', 'mp3', 'flac', 'ogg', 'm4a'],
  视频: ['mp4', 'mkv', 'mov', 'webm'],
  压缩包: ['zip', '7z', 'rar', 'tar', 'gz'],
};
export function makeFileOperations(paths: string[], mode: string, directory: string, name: string): FileOperation[] {
  return paths.map((source, index) => {
    const parts = source.split('/'), filename = parts.pop()!;
    const extension = filename.split('.').pop()!.toLowerCase();
    const category = Object.entries(categories).find(([, extensions]) => extensions.includes(extension))?.[0] ?? '其他';
    const folder = mode === 'rename' ? parts.join('/') : mode === 'organize' ? [directory, category].filter(Boolean).join('/') : directory;
    const output = mode === 'rename' ? paths.length === 1 ? name : `${name}${index + 1}_${filename}` : filename;
    return { kind: mode === 'copy' ? 'copy' : 'move', source, target: [folder, output].filter(Boolean).join('/') };
  });
}
