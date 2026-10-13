import { _electron as electron, expect, test } from '@playwright/test';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

interface ChatMessage { role: string; content?: string; tool_call_id?: string; tool_calls?: { id: string; function: { name: string } }[] }

// Deterministic local protocol fixture. It does not measure LLM planning quality.
async function modelFixture() {
  let calls = 0, requests = 0;
  const server = createServer(async (request, response) => {
    requests++;
    const buffers: Buffer[] = [];
    for await (const chunk of request) buffers.push(Buffer.from(chunk));
    const body = JSON.parse(Buffer.concat(buffers).toString()) as { messages: ChatMessage[] };
    const messages = body.messages;
    const lastUser = messages.map(m => m.role).lastIndexOf('user');
    const names = new Map(messages.flatMap(m => (m.tool_calls ?? []).map(c => [c.id, c.function.name] as const)));
    const results = messages.filter(m => m.role === 'tool').map(m => ({ name: names.get(m.tool_call_id!), data: JSON.parse(m.content!).data }));
    const turnResults = messages.slice(lastUser + 1).filter(m => m.role === 'tool').map(m => ({ name: names.get(m.tool_call_id!), data: JSON.parse(m.content!).data }));
    const latest = (name: string) => [...results].reverse().find(r => r.name === name)?.data;
    let text = '', actions: { name: string; arguments: string }[] = [];
    const action = (name: string, args: object) => ({ name, arguments: JSON.stringify(args) });
    const roots = latest('list_workspace_roots') as { id: string }[] | undefined;
    if (messages[lastUser].content?.includes('核对')) {
      const note = latest('propose_workspace_note') as { root_id: string; plan_id: string; target: string };
      if (!turnResults.length) actions = [action('workspace_file_status', { root_id: note.root_id, plan_id: note.plan_id })];
      else if (turnResults.length === 1) actions = [action('read_workspace_text', { root_id: note.root_id, path: note.target })];
      else text = '已根据真实执行状态和目标文件内容核对保存结果。';
    } else if (!turnResults.length) actions = [action('list_workspace_roots', {})];
    else if (!roots?.length) text = '当前没有共享资料目录，请先选择资料目录。';
    else if (turnResults.length === 1) actions = ['asyncio.md', 'task.md'].map(path => action('read_workspace_text', { root_id: roots[0].id, path }));
    else if (!turnResults.some(r => r.name === 'propose_workspace_note')) {
      const reads = turnResults.filter(r => r.name === 'read_workspace_text');
      const text = '# asyncio复习\n\n先给直觉：等待期间让其他任务继续。\n\n' + reads.map(r => `${r.data.text}\n来源：${r.data.path}#行1`).join('\n\n') + '\n';
      actions = [action('propose_workspace_note', { root_id: roots[0].id, target: '复习/asyncio提纲.md', text })];
    } else text = '笔记已暂存，等待你确认，尚未保存。';
    const tool_calls = actions.map((a, index) => ({ index, id: `local_${++calls}`, type: 'function', function: a }));
    const chunk = (delta: object, finish_reason: string | null) => JSON.stringify({ id: 'local-fixture', object: 'chat.completion.chunk', created: 1, model: 'local-fixture', choices: [{ index: 0, delta, finish_reason }] });
    response.writeHead(200, { 'Content-Type': 'text/event-stream' });
    response.end(`data: ${chunk({ role: 'assistant', content: text || null, ...(tool_calls.length ? { tool_calls } : {}) }, null)}\n\ndata: ${chunk({}, tool_calls.length ? 'tool_calls' : 'stop')}\n\ndata: [DONE]\n\n`);
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  return { url: `http://127.0.0.1:${(server.address() as AddressInfo).port}/v1`, requests: () => requests, close: () => new Promise<void>(resolve => server.close(() => resolve())) };
}

async function launchCase() {
  const project = resolve(import.meta.dirname, '../../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 笔记对话 '));
  const source = join(folder, '资料'); await mkdir(source);
  await writeFile(join(source, 'asyncio.md'), '协程可以在等待时让出执行权。');
  await writeFile(join(source, 'task.md'), 'Task负责调度协程，不等同于线程。');
  const model = await modelFixture();
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['DEEPSEEK_API_KEY', 'ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'openai', HERTA_DESKTOP_DATA_DIR: join(folder, 'data'), HERTA_BASE_URL: model.url, HERTA_MODEL: 'local-fixture', HERTA_API_KEY: 'local-fixture-only', PYTHONPATH: join(project, 'backend') } as Record<string, string>;
  const seed = spawnSync(join(project, '.venv/Scripts/python.exe'), ['-c', 'from pathlib import Path; import sys; from herta_agent.companion.store import CompanionStore; p=Path(sys.argv[1]); p.mkdir(); s=CompanionStore(p/"companionship.sqlite3"); s.personal.voice("piper","neutral")', env.HERTA_DESKTOP_DATA_DIR], { cwd: project, env, windowsHide: true });
  expect(seed.status).toBe(0);
  const desktop = await electron.launch({ args: [join(project, 'frontend')], env, cwd: folder });
  const page = await desktop.firstWindow();
  await expect(page.getByRole('status').first()).toHaveText('服务就绪', { timeout: 20000 });
  await desktop.evaluate(({ dialog }, path) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] }); dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false }); }, source);
  return { desktop, page, source, requests: model.requests, close: async () => { await desktop.close(); await model.close(); await rm(folder, { recursive: true, force: true }); } };
}

test('chat reads real material, previews, cancels then confirms and verifies the saved note', async () => {
  const app = await launchCase();
  try {
    await app.page.getByRole('button', { name: '选择资料目录', exact: true }).click();
    await app.page.getByRole('textbox', { name: '消息' }).fill('根据两份笔记整理提纲，保留来源，保存前给我确认');
    await app.page.getByRole('button', { name: '发送', exact: true }).click();
    const task = app.page.getByRole('region', { name: '笔记保存任务' });
    await expect(task).toContainText('来源：asyncio.md#行1', { timeout: 20000 });
    await expect(task).toContainText('来源：task.md#行1');
    const output = join(app.source, '复习/asyncio提纲.md');
    await expect(readFile(output)).rejects.toThrow();
    await app.desktop.evaluate(({ dialog }) => { dialog.showMessageBox = async () => ({ response: 0, checkboxChecked: false }); });
    await task.getByRole('button', { name: '确认保存笔记' }).click();
    await expect(task).toContainText('已取消确认，文件未保存');
    await expect(readFile(output)).rejects.toThrow();
    await app.desktop.evaluate(({ dialog }) => { dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false }); });
    await app.page.getByRole('textbox', { name: '消息' }).fill('保留未发送草稿');
    await task.getByRole('button', { name: '确认保存笔记' }).click();
    await expect(task).toContainText('已保存并读取目标文件', { timeout: 15000 });
    expect(await readFile(output, 'utf8')).toContain('Task负责调度协程');
    expect(await readFile(join(app.source, 'asyncio.md'), 'utf8')).toBe('协程可以在等待时让出执行权。');
    await expect(app.page.locator('.assistant-message').last()).toContainText('已根据真实执行状态', { timeout: 15000 });
    await expect(app.page.getByRole('textbox', { name: '消息' })).toHaveValue('保留未发送草稿');
    const requests = app.requests();
    await app.page.reload();
    await app.page.getByRole('button', { name: /根据两份笔记整理提纲/ }).click();
    await expect(app.page.getByRole('region', { name: '笔记保存任务' })).toContainText('已保存并读取目标文件', { timeout: 15000 });
    await app.page.waitForTimeout(250);
    expect(app.requests()).toBe(requests);
  } finally { await app.close(); }
});

test('chat note cannot overwrite an existing target or execute after sharing is revoked', async () => {
  const app = await launchCase();
  try {
    await mkdir(join(app.source, '复习'));
    await writeFile(join(app.source, '复习/asyncio提纲.md'), '保留原文');
    await app.page.getByRole('button', { name: '选择资料目录', exact: true }).click();
    await app.page.getByRole('textbox', { name: '消息' }).fill('整理两份笔记，保存前确认');
    await app.page.getByRole('button', { name: '发送', exact: true }).click();
    const task = app.page.getByRole('region', { name: '笔记保存任务' });
    await expect(task).toContainText('目标已存在', { timeout: 20000 });
    await expect(task.getByRole('button', { name: '确认保存笔记' })).toBeDisabled();
    expect(await readFile(join(app.source, '复习/asyncio提纲.md'), 'utf8')).toBe('保留原文');
    const roots = await app.page.evaluate(() => window.herta.workspace.roots());
    await app.page.evaluate(id => window.herta.workspace.share(id, false), roots[0].id);
    await task.getByRole('button', { name: '刷新保存状态' }).click();
    await expect(task).toContainText('未允许聊天读取');
    expect(await readFile(join(app.source, '复习/asyncio提纲.md'), 'utf8')).toBe('保留原文');
  } finally { await app.close(); }
});

test('a stale successful refresh cannot replace a newer sharing revocation', async () => {
  const app = await launchCase();
  try {
    await app.page.getByRole('button', { name: '选择资料目录', exact: true }).click();
    await app.page.getByRole('textbox', { name: '消息' }).fill('整理两份笔记，保存前确认');
    await app.page.getByRole('button', { name: '发送', exact: true }).click();
    const task = app.page.getByRole('region', { name: '笔记保存任务' });
    await expect(task.getByRole('button', { name: '确认保存笔记' })).toBeEnabled({ timeout: 20000 });
    await task.getByRole('button', { name: '确认保存笔记' }).click();
    await expect(task).toContainText('已保存并读取目标文件', { timeout: 15000 });
    await app.page.getByRole('textbox', { name: '消息' }).fill('保留草稿');
    await expect(app.page.getByRole('button', { name: '发送', exact: true })).toBeEnabled();
    await app.desktop.evaluate(() => {
      const state = globalThis as typeof globalThis & { held?: boolean; releaseRead?: () => void };
      const original = globalThis.fetch;
      let once = true;
      globalThis.fetch = async (...args) => {
        const result = await original(...args);
        if (once && String(args[0]).includes('/text?') && String(args[0]).includes('shared=true')) {
          once = false; state.held = true;
          await new Promise<void>(resolve => { state.releaseRead = resolve; });
        }
        return result;
      };
    });
    await task.getByRole('button', { name: '刷新保存状态' }).click();
    await expect.poll(() => app.desktop.evaluate(() => (globalThis as typeof globalThis & { held?: boolean }).held)).toBe(true);
    const roots = await app.page.evaluate(() => window.herta.workspace.roots());
    await app.page.evaluate(id => window.herta.workspace.share(id, false), roots[0].id);
    await task.getByRole('button', { name: '刷新保存状态' }).click();
    await expect(task).toContainText('未允许聊天读取');
    await app.desktop.evaluate(() => (globalThis as typeof globalThis & { releaseRead?: () => void }).releaseRead?.());
    await app.page.waitForTimeout(250);
    await expect(task).not.toContainText('已保存并读取目标文件');
    await expect(task).toContainText('未允许聊天读取');
  } finally { await app.close(); }
});

test('a rejected save continuation remains retryable without losing the draft', async () => {
  const app = await launchCase();
  try {
    await app.page.getByRole('button', { name: '选择资料目录', exact: true }).click();
    await app.page.getByRole('textbox', { name: '消息' }).fill('整理两份笔记，保存前确认');
    await app.page.getByRole('button', { name: '发送', exact: true }).click();
    const task = app.page.getByRole('region', { name: '笔记保存任务' });
    await expect(task.getByRole('button', { name: '确认保存笔记' })).toBeEnabled({ timeout: 20000 });
    await app.page.getByRole('textbox', { name: '消息' }).fill('保留未发送草稿');
    await app.desktop.evaluate(() => {
      const original = globalThis.fetch;
      let once = true;
      globalThis.fetch = async (...args) => {
        if (once && String(args[0]).includes('/runs') && String(args[1]?.body).includes('[保存后核对]')) {
          once = false; return new Response('{}', { status: 503 });
        }
        return original(...args);
      };
    });
    await task.getByRole('button', { name: '确认保存笔记' }).click();
    await expect(app.page.locator('.notice.error')).toContainText('暂不可用', { timeout: 15000 });
    await expect(app.page.getByRole('textbox', { name: '消息' })).toHaveValue('保留未发送草稿');
    await task.getByRole('button', { name: '让 Herta 核对结果' }).click();
    await expect(app.page.locator('.assistant-message').last()).toContainText('已根据真实执行状态', { timeout: 15000 });
    await expect(app.page.getByRole('textbox', { name: '消息' })).toHaveValue('保留未发送草稿');
  } finally { await app.close(); }
});
