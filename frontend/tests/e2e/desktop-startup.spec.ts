import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { mkdtemp, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { spawn } from 'node:child_process';
import electronPath from 'electron';

const root = resolve(import.meta.dirname, '../../..');
let folder: string;
let desktop: ElectronApplication | undefined;

function alive(pid: number) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

function environment(provider = 'demo') {
  return {
    ...Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))),
    HERTA_SERVICE_PROVIDER: provider, HERTA_DESKTOP_DATA_DIR: join(folder, '桌面 数据'),
  } as Record<string, string>;
}

async function launch(env = environment(), appPath = join(root, 'frontend')) {
  desktop = await electron.launch({ args: [appPath], env, cwd: folder });
  return desktop.firstWindow();
}

async function owned() {
  return desktop!.evaluate(({ app }) => {
    const module = process.getBuiltinModule('module');
    const { backend } = module.createRequire(app.getAppPath() + '/package.json')('./dist/electron/main.cjs');
    return { pid: backend.pid as number, launcher: backend.launcherPid as number, endpoint: backend.endpoint as string };
  });
}

test.beforeEach(async () => { folder = await mkdtemp(join(tmpdir(), 'Herta 中文 空格 ')); });
test.afterEach(async () => {
  if (desktop) { await desktop.close(); desktop = undefined; }
  await rm(folder, { recursive: true, force: true });
});

test('three real window cycles from outside cwd; owned Python exits and SQLite reopens', async () => {
  await symlink(root, join(folder, '项目 空格'), 'junction');
  for (let i = 0; i < 3; i++) {
    const env = { ...environment(), HERTA_DESKTOP_PYTHON: join(folder, '项目 空格/.venv/Scripts/python.exe') };
    const page = await launch(env);
    await expect(page.getByRole('heading', { name: 'Herta', exact: true })).toBeVisible();
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    await expect(page.getByRole('textbox')).toBeEnabled();
    const state = await owned();
    expect(alive(state.pid)).toBe(true);
    const health = await fetch(state.endpoint + '/health').then(r => r.json());
    expect(health.chat_available).toBe(true);
    expect(await page.evaluate(() => ({
      node: typeof (window as unknown as { require?: unknown }).require,
      bridge: Object.keys(window.herta),
    }))).toEqual({ node: 'undefined', bridge: ['getBackendStatus', 'listSessions', 'createSession', 'getSession', 'getRun', 'startRun', 'cancelRequest', 'onRunEvents', 'onBackendStatus'] });
    if (i === 0) await page.screenshot({ path: join(root, '.local/phase6-stage1-window.png') });
    const exited = desktop!.waitForEvent('close');
    await desktop!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
    await exited;
    desktop = undefined;
    await expect.poll(() => alive(state.pid) || alive(state.launcher)).toBe(false);
    await expect.poll(async () => {
      try { await fetch(state.endpoint + '/health'); return true; } catch { return false; }
    }).toBe(false);
  }
});

test('missing model config remains connected and visibly read only', async () => {
  const page = await launch(environment('openai'));
  await expect(page.getByRole('status')).toHaveText('配置未就绪');
  const state = await owned();
  expect((await fetch(state.endpoint + '/health').then(r => r.json())).chat_available).toBe(false);
});

test('missing interpreter produces safe visible error', async () => {
  const page = await launch({ ...environment(), HERTA_DESKTOP_PYTHON: join(folder, 'missing.exe') });
  await expect(page.getByRole('status')).toHaveText('后端不可用');
  await expect(page.getByText('Python 后端启动失败，请检查本地环境后重新打开应用。')).toBeVisible();
});

test('second launch activates existing window without another backend', async () => {
  const env = environment();
  const page = await launch(env);
  await expect(page.getByRole('status')).toHaveText('服务就绪');
  const original = await owned();
  await desktop!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].minimize());
  const duplicate = spawn(electronPath as unknown as string, [join(root, 'frontend')], { env, cwd: folder, windowsHide: true, stdio: 'ignore' });
  await new Promise<void>((resolve, reject) => {
    duplicate.on('error', reject);
    duplicate.on('exit', code => code === 0 ? resolve() : reject(new Error('duplicate did not exit cleanly')));
  });
  await expect.poll(() => desktop!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isMinimized())).toBe(false);
  expect(await owned()).toEqual(original);
  expect(desktop!.windows()).toHaveLength(1);
});

test('unexpected Python exit invalidates ready state', async () => {
  const page = await launch();
  await expect(page.getByRole('status')).toHaveText('服务就绪');
  const state = await owned();
  process.kill(state.pid);
  await expect(page.getByRole('status')).toHaveText('后端不可用');
});

test('shutdown failure or stall cannot retain Electron and its instance lock', async () => {
  test.setTimeout(90000);
  for (const failure of ['reject', 'stall']) {
    const page = await launch();
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    const state = await owned();
    const mainPid = desktop!.process().pid!;
    await desktop!.evaluate(async ({ app }, failure) => {
      const module = process.getBuiltinModule('module');
      const { backend } = module.createRequire(app.getAppPath() + '/package.json')('./dist/electron/main.cjs');
      if (failure === 'reject') {
        await backend.stop();
        backend.stop = () => Promise.reject(new Error('injected shutdown failure'));
      } else {
        backend.stop = () => new Promise(() => {});
      }
    }, failure);
    await desktop!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
    await expect.poll(() => alive(mainPid), { timeout: 45000 }).toBe(false);
    desktop = undefined;
    await expect.poll(() => alive(state.pid) || alive(state.launcher)).toBe(false);
  }
  const page = await launch();
  await expect(page.getByRole('status')).toHaveText('服务就绪');
});
