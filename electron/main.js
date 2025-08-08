
const { app, BrowserWindow, Notification, dialog, ipcMain, Menu } = require('electron');

// Disable GPU and hardware acceleration early to avoid EGL/ANGLE issues on Linux
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
// Removed to allow software rasterizer fallback to work properly
// app.commandLine.appendSwitch('disable-software-rasterizer');
app.commandLine.appendSwitch('disable-webgpu');
app.commandLine.appendSwitch('use-gl', 'swiftshader');
app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
const path = require('path');
const fs = require('fs');
const { PythonProcessManager } = require('./pythonProcessManager');
const { store, getUserDataPath } = require('./store');
const settingsStore = require('./settingsStore');
const http = require('http');
const { createApiClient } = require('./apiClient');

let processManager = null;
let isShuttingDown = false;
let pendingBackendUrl = null;
let triedAlternateHost = false;
let mainWindow = null;
let settingsWindow = null;
// Managed by PythonProcessManager

// API client (uses resolveBackendBaseUrl which is hoisted below)
const apiClient = createApiClient({ resolveBaseUrl: resolveBackendBaseUrl, logger: console });

function buildWebviewWrapperDataUrl(url) {
  const html = `<!doctype html>
  <html>
    <head>
      <meta charset="utf-8" />
      <meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' 'unsafe-eval' http: https: data: blob:; img-src * data: blob:; media-src * data: blob:; connect-src * data: blob:; frame-src * data: blob:;" />
      <title>TypeComplex (wrapper)</title>
      <style>
        html,body{height:100%;margin:0;padding:0}
        #bar{position:fixed;left:0;right:0;top:0;height:28px;background:#f6f6f6;border-bottom:1px solid #ddd;display:flex;align-items:center;font:12px/1.2 system-ui;padding:0 8px;color:#333;gap:8px}
        #webview{position:absolute;top:28px;left:0;right:0;bottom:0;width:100%;height:calc(100% - 28px)}
        code{background:#eee;padding:2px 4px;border-radius:4px}
      </style>
    </head>
    <body>
      <div id="bar">Loading in webview wrapper → <code id="u"></code></div>
      <webview id="webview" src="${url}" allowpopups></webview>
      <script>
        const u = document.getElementById('u');
        u.textContent = '${url}'.replace(/&/g,'&').replace(/</g,'<');
        const wv = document.getElementById('webview');
        const log = (ev, extra) => console.log('[webview]', ev, extra || '');
        ['did-start-loading','did-stop-loading','did-finish-load','dom-ready','console-message','did-fail-load','will-navigate','did-navigate'].forEach(ev => wv.addEventListener(ev, (e) => log(ev)));
        wv.addEventListener('dom-ready', () => { try { wv.openDevTools(); } catch(_) {} });
      </script>
    </body>
  </html>`;
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false, // Keep false for security
      contextIsolation: true, // Keep true for security
      sandbox: true,
      webSecurity: true,
      webgl: false, // reduce GPU use in renderer
      webviewTag: false, // not needed for local UI
    },
    backgroundColor: '#ffffff',
    show: false,
  });

  // Debug load events to diagnose white screen
  mainWindow.webContents.on('will-navigate', (event, url) => {
    console.log('will-navigate', { url, current: mainWindow.webContents.getURL() });
  });
  mainWindow.webContents.on('did-start-navigation', (event, url, isInPlace, isMainFrame) => {
    console.log('did-start-navigation', { url, isInPlace, isMainFrame, current: mainWindow.webContents.getURL() });
  });
  mainWindow.webContents.on('did-redirect-navigation', (event, url, isInPlace, isMainFrame) => {
    console.log('did-redirect-navigation', { url, isInPlace, isMainFrame, current: mainWindow.webContents.getURL() });
  });
  mainWindow.webContents.on('did-navigate', (event, url, httpResponseCode, httpStatusText) => {
    console.log('did-navigate', { url, httpResponseCode, httpStatusText, current: mainWindow.webContents.getURL() });
  });
  mainWindow.webContents.on('did-navigate-in-page', (event, url, isMainFrame, frameProcessId, frameRoutingId) => {
    console.log('did-navigate-in-page', { url, isMainFrame, current: mainWindow.webContents.getURL() });
  });
  mainWindow.webContents.on('did-commit-navigation', (event, url, isInPlace, isMainFrame) => {
    console.log('did-commit-navigation', { url, isInPlace, isMainFrame, current: mainWindow.webContents.getURL() });
  });
  mainWindow.webContents.on('did-fail-load', (e, code, desc, url, isMainFrame) => {
    console.error('did-fail-load', { code, desc, url, isMainFrame });
    if (isMainFrame && pendingBackendUrl) {
      const alt = pendingBackendUrl.replace('127.0.0.1', 'localhost');
      if (!triedAlternateHost && alt !== pendingBackendUrl) {
        triedAlternateHost = true;
        console.warn('Retrying load with localhost instead of 127.0.0.1');
        mainWindow.loadURL(alt).catch((err) => console.error('Alternate host load failed:', err));
        return;
      }
      // Fallback to a basic page so the window is not blank
      mainWindow.loadURL('data:text/html,<h2>Backend unreachable</h2><p>Check console logs. Retrying in 5s...</p>');
      setTimeout(() => {
        mainWindow.loadURL(pendingBackendUrl).catch(() => {});
      }, 5000);
    }
  });
  mainWindow.webContents.on('did-fail-provisional-load', (e, code, desc, url, isMainFrame) => {
    console.error('did-fail-provisional-load', { code, desc, url, isMainFrame });
  });
  mainWindow.webContents.on('did-finish-load', () => {
    console.log('Renderer finished load');
  });
  mainWindow.webContents.on('dom-ready', () => {
    console.log('Renderer DOM ready');
    if (!mainWindow.webContents.isDevToolsOpened()) {
      mainWindow.webContents.openDevTools({ mode: 'detach' });
    }
  });
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    console.log('renderer console:', { level, message, line, sourceId });
  });

  // Do not load local UI; we'll navigate to backend when ready

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createSettingsWindow() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    try { settingsWindow.focus(); } catch (_) {}
    return settingsWindow;
  }
  settingsWindow = new BrowserWindow({
    width: 720,
    height: 560,
    resizable: true,
    title: 'Settings',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
    backgroundColor: '#ffffff',
    show: true,
  });
  const htmlPath = path.join(__dirname, 'renderer', 'settings.html');
  settingsWindow.loadFile(htmlPath).catch((e) => console.error('Failed to load settings window:', e));
  settingsWindow.on('closed', () => {
    settingsWindow = null;
  });
  return settingsWindow;
}

function buildAppMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: () => createSettingsWindow() },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    }] : []),
    {
      label: 'File',
      submenu: [
        ...(isMac ? [] : [{ label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: () => createSettingsWindow() }]),
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit' },
      ],
    },
    { label: 'Edit', submenu: [ { role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' } ] },
    { label: 'View', submenu: [ { role: 'reload' }, { role: 'toggleDevTools' }, { type: 'separator' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' }, { role: 'togglefullscreen' } ] },
    { label: 'Window', submenu: [ { role: 'minimize' }, { role: 'zoom' }, ...(isMac ? [{ type: 'separator' }, { role: 'front' }] : [{ role: 'close' }]) ] },
    { label: 'Help', submenu: [] },
  ];
  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function startBackend() {
  // Prefer running the Python entrypoint in dev; packaged binary can be set later
  const userData = getUserDataPath();
  processManager = new PythonProcessManager({ logDir: path.join(userData, 'logs') });

  processManager.on('stdout', (msg) => console.log(`Flask stdout: ${msg}`));
  processManager.on('stderr', (msg) => console.error(`Flask stderr: ${msg}`));
  processManager.on('ready', async ({ url }) => {
    console.log('Backend ready at', url);
    pendingBackendUrl = url;
    store.set('process.lastReadyAt', Date.now());
    store.set('process.cooldownUntil', 0);
    // Navigate to the backend Web UI once ready, keeping preload security settings
    if (mainWindow && !mainWindow.isDestroyed()) {
      // Show window after first successful load
      const showOnceOnLoad = () => {
        try {
          if (!mainWindow.isVisible()) mainWindow.show();
        } catch (_) {}
      };
      mainWindow.webContents.once('did-finish-load', showOnceOnLoad);
      try {
        await mainWindow.loadURL(url);
      } catch (e) {
        console.error('Load failed on ready:', e);
      }
      // Try alternate host shortly after, if still not navigated
      setTimeout(async () => {
        try {
          const current = mainWindow.webContents.getURL();
          if (!current || current.startsWith('file://')) {
            const alt = url.replace('127.0.0.1', 'localhost');
            console.warn('Retrying navigation to backend (alt host)...');
            await mainWindow.loadURL(alt);
          }
        } catch (err) {
          console.error('Retry load error:', err);
        }
      }, 1200);
    }

    // Probe AI readiness once on backend ready and surface guidance if needed
    try {
      const healthUrl = url.replace(/\/$/, '') + '/health?probe_ai=1';
      const req = http.get(healthUrl, (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => {
          try {
            const data = JSON.parse(body || '{}');
            const ai = (data && data.ai) ? data.ai : null;
            if (ai && ai.key_status === 'unset') {
              notify('AI features are disabled', 'Add your DeepSeek API key in Settings to enable AI suggestions.');
              // Auto-open settings once per session when key is unset on first readiness
              try {
                const lastAuto = store.get('ui.lastAutoOpenedSettingsAt', 0);
                if (!lastAuto || (Date.now() - Number(lastAuto)) > 10_000) {
                  store.set('ui.lastAutoOpenedSettingsAt', Date.now());
                  createSettingsWindow();
                }
              } catch (_) {}
            } else if (ai && ai.key_status === 'set' && ai.ready === false) {
              notify('AI not ready', 'DeepSeek connectivity failed. Check your API key or network, then try again.');
            }
          } catch (e) {
            console.warn('Failed to parse health JSON for AI readiness:', e && e.message ? e.message : e);
          }
        });
      });
      req.on('error', (e) => {
        console.warn('AI readiness probe error:', e && e.message ? e.message : e);
      });
    } catch (_) {}
  });

  // If backend reports unhealthy, keep local UI visible
  processManager.on('unhealthy', () => {
    // no-op
  });
  processManager.on('restarting', ({ attempt, delay, cause }) => {
    const body = `Restarting backend in ${Math.round(delay/1000)}s (attempt ${attempt}/${processManager.maxRestartAttempts}). Cause: ${cause || 'unknown'}`;
    console.log(body);
    notify('TypeComplex backend', body);
    store.set('process.lastRestart', { at: Date.now(), attempt, delay, cause });
  });
  processManager.on('heartbeat-restart', () => {
    const msg = 'Heartbeat: restarting backend due to repeated health failures';
    console.warn(msg);
    notify('TypeComplex backend', msg);
  });
  processManager.on('exit', ({ code, signal, cause }) => {
    store.set('process.lastExit', { at: Date.now(), code, signal, cause });
  });
  processManager.on('failed', ({ message, reason, cooldownMs, cooldownUntil, logFile }) => {
    const until = cooldownUntil ? new Date(cooldownUntil).toLocaleTimeString() : '';
    const body = message || `Backend failure (${reason || 'unknown'}).`;
    console.error('Backend failed:', { reason, cooldownMs, cooldownUntil, logFile });
    store.set('process.cooldownUntil', cooldownUntil || 0);
    // Notification with simple action guidance
    notify('TypeComplex backend', `${body} Will retry after cooldown${until ? ' until ' + until : ''}.`);
    if (mainWindow) {
      const extra = logFile ? ` (logs at: ${logFile})` : '';
      mainWindow.loadURL(`data:text/html,<h1>Backend recovery</h1><p>${body}${extra}</p><p>Will retry after cooldown.</p>`);
    }
  });
  processManager.on('error', (err) => console.error('Flask process error:', err));

  const cooldownUntil = Number(store.get('process.cooldownUntil', 0));
  if (cooldownUntil && Date.now() < cooldownUntil) {
    const ms = cooldownUntil - Date.now();
    const msg = `Delaying backend start due to cooldown (${Math.ceil(ms/1000)}s)`;
    console.warn(msg);
    notify('TypeComplex backend', msg);
    setTimeout(() => processManager.start(), ms);
  } else {
    processManager.start();
  }
}

function waitForHealth(url, timeoutMs = 20000, intervalMs = 300) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    function check() {
      const req = http.get(url, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
        res.resume();
      });
      req.on('error', retry);
      function retry() {
        if (Date.now() - start > timeoutMs) {
          reject(new Error('Health check timed out'));
          return;
        }
        setTimeout(check, intervalMs);
      }
    }
    check();
  });
}

function pollHealthAndNavigate({ hosts = ['127.0.0.1', 'localhost'], port = 5001, path = '/health' } = {}) {
  const start = Date.now();
  const maxMs = 180000; // 3 minutes
  const interval = 500; // poll frequency
  let stopped = false;
  const tryOnce = () => {
    if (stopped) return;
    if (Date.now() - start > maxMs) {
      console.warn('Health polling (main) timed out');
      return;
    }
    let remaining = hosts.slice();
    const tryNext = () => {
      if (stopped) return;
      const host = remaining.shift();
      if (!host) {
        setTimeout(tryOnce, interval);
        return;
      }
      const url = `http://${host}:${port}${path}`;
      try {
        const req = http.get(url, (res) => {
          res.resume();
          if (res.statusCode === 200) {
            const base = `http://${host}:${port}`;
            console.log('Health (main) OK, navigating to', base);
            if (mainWindow && !mainWindow.isDestroyed()) {
              stopped = true;
              mainWindow.loadURL(base).catch((e) => console.error('Navigation error after health OK:', e));
            }
          } else {
            tryNext();
          }
        });
        req.on('error', tryNext);
      } catch (_) {
        tryNext();
      }
    };
    tryNext();
  };
  tryOnce();
  return () => { stopped = true; };
}

app.on('ready', async () => {
  startBackend();
  createWindow();
  try { buildAppMenu(); } catch (e) { console.warn('Menu build failed:', e && e.message ? e.message : e); }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (isShuttingDown) return;
    isShuttingDown = true;
    if (processManager) {
      Promise.resolve(processManager.stop({ timeoutMs: 8000 })).finally(() => app.quit());
    } else {
      app.quit();
    }
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

app.on('before-quit', () => {
  if (isShuttingDown) return;
  isShuttingDown = true;
  if (processManager) {
    try { processManager.stop({ timeoutMs: 8000 }); } catch (_) {}
  }
});

process.on('uncaughtException', (err) => {
  console.error('Uncaught exception:', err);
  if (!isShuttingDown && processManager) {
    isShuttingDown = true;
    try { processManager.stop({ timeoutMs: 3000 }); } catch (_) {}
  }
});

process.on('unhandledRejection', (reason) => {
  console.error('Unhandled rejection:', reason);
  if (!isShuttingDown && processManager) {
    isShuttingDown = true;
    try { processManager.stop({ timeoutMs: 3000 }); } catch (_) {}
  }
});

function notify(title, body) {
  try {
    if (Notification && Notification.isSupported && Notification.isSupported()) {
      const n = new Notification({ title, body });
      n.show();
      return;
    }
  } catch (_) {}
  try {
    dialog.showMessageBox({ type: 'info', title, message: body });
  } catch (_) {}
}

// IPC: health check (renderer -> main)
ipcMain.handle('health:check', async () => {
  const hosts = ['127.0.0.1', 'localhost'];
  const port = 5001;
  const pathName = '/health';
  for (const host of hosts) {
    const url = `http://${host}:${port}${pathName}`;
    try {
      await waitForHealth(url, 2000, 200);
      // Fetch once for payload
      const data = await new Promise((resolve, reject) => {
        try {
          const req = http.get(url, (res) => {
            let body = '';
            res.setEncoding('utf8');
            res.on('data', (c) => { body += c; });
            res.on('end', () => {
              try { resolve(JSON.parse(body || '{}')); } catch (_) { resolve({}); }
            });
          });
          req.on('error', reject);
        } catch (e) { reject(e); }
      });
      return { ok: true, baseUrl: `http://${host}:${port}`, data };
    } catch (_) {
      // try next host
    }
  }
  return { ok: false, error: 'Backend not reachable on 127.0.0.1 or localhost:5001' };
});

// IPC: settings window open
ipcMain.handle('settings:openWindow', async () => {
  try { createSettingsWindow(); return { ok: true }; } catch (e) { return { ok: false, error: e && e.message ? e.message : String(e) }; }
});

// IPC: preferences get/set (non-secret)
ipcMain.handle('settings:getPrefs', async () => {
  try { return settingsStore.getPrefs(); } catch (e) { return settingsStore.getPrefs(); }
});
ipcMain.handle('settings:setPrefs', async (_event, { partial } = {}) => {
  try { return settingsStore.setPrefs(partial || {}); } catch (e) { return settingsStore.getPrefs(); }
});

// IPC: API key management (delegates to backend; never logs key)
ipcMain.handle('settings:getKeyStatus', async () => {
  try {
    const r = await apiClient.request('/settings/api-key/status', { method: 'GET', timeoutMs: 5000 });
    const status = (r && r.ok && r.data && r.data.status) ? r.data.status : 'unset';
    // persist masked status locally for UI hints
    settingsStore.setPrefs({ deepseekKeyStatus: status });
    return { status };
  } catch (e) {
    return { status: 'unset', error: e && e.message ? e.message : String(e) };
  }
});

ipcMain.handle('settings:setApiKey', async (_event, { key } = {}) => {
  try {
    if (typeof key !== 'string' || key.length < 10) throw new Error('invalid_key');
    const r = await apiClient.request('/settings/api-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key }),
      timeoutMs: 8000,
    });
    if (!r || !r.ok) {
      return { ok: false, error: (r && (r.message || (r.data && (r.data.error || r.data.message)))) || 'set_failed' };
    }
    settingsStore.setPrefs({ deepseekKeyStatus: 'set' });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
});

ipcMain.handle('settings:testApiKey', async () => {
  try {
    const r = await apiClient.request('/settings/api-key/test', { method: 'POST', timeoutMs: 8000 });
    if (!r || !r.ok) {
      return { ok: false, error: (r && (r.message || (r.data && (r.data.error || r.data.message)))) || 'test_failed' };
    }
    const json = r.data || {};
    return { ok: Boolean(json && json.ok), error: json && json.error ? json.error : null };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
});

ipcMain.handle('settings:deleteApiKey', async () => {
  try {
    const r = await apiClient.request('/settings/api-key', { method: 'DELETE', timeoutMs: 8000 });
    if (!r || !r.ok) {
      const json = r && r.data ? r.data : {};
      return { ok: false, error: (json && (json.error || json.message)) || (r.message || 'delete_failed') };
    }
    settingsStore.setPrefs({ deepseekKeyStatus: 'unset' });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
});

// IPC: open PDF dialog (renderer -> main)
ipcMain.handle('file:openPdf', async () => {
  try {
    const result = await dialog.showOpenDialog({
      properties: ['openFile'],
      filters: [{ name: 'PDF Files', extensions: ['pdf'] }],
    });
    if (result.canceled || !result.filePaths || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  } catch (_) {
    return null;
  }
});

// --- Helpers for PDF processing ---
async function resolveBackendBaseUrl() {
  if (pendingBackendUrl) return pendingBackendUrl.replace(/\/$/, '');
  const hosts = ['127.0.0.1', 'localhost'];
  const port = 5001;
  const pathName = '/health';
  for (const host of hosts) {
    const url = `http://${host}:${port}${pathName}`;
    try {
      await waitForHealth(url, 2000, 200);
      return `http://${host}:${port}`;
    } catch (_) {
      // try next host
    }
  }
  throw new Error('Backend not reachable on 127.0.0.1 or localhost:5001');
}

function isPdfPath(filePath) {
  try {
    if (!filePath || typeof filePath !== 'string') return false;
    if (!fs.existsSync(filePath)) return false;
    return (/\.pdf$/i).test(filePath);
  } catch (_) { return false; }
}

const activeTasks = new Map(); // taskId -> { stop: boolean, webContentsId }

async function uploadPdfAndGetTaskId(baseUrl, filePath, options = {}) {
  const defaults = {
    action: 'full_analysis',
    target_audience: 'Standard',
    analysis_mode: 'best',
    include_overview_page: true,
    overview_top_x_count: 5,
    overview_top_x_type: 'complex',
    overview_show_visual_map: true,
  };
  const opts = { ...defaults, ...options };

  // Build multipart/form-data with Blob to avoid extra deps
  const buf = await fs.promises.readFile(filePath);
  const blob = new Blob([buf], { type: 'application/pdf' });
  const form = new FormData();
  form.append('file', blob, path.basename(filePath));
  for (const [k, v] of Object.entries(opts)) {
    form.append(k, String(v));
  }

  const r = await apiClient.request('/upload_pdf', { method: 'POST', body: form, timeoutMs: 30000 });
  if (!r || !r.ok) {
    const status = r && typeof r.status === 'number' ? r.status : '0';
    const msg = (r && (r.message || (r.data && (r.data.error || r.data.message)))) || 'unknown error';
    throw new Error(`Upload failed (${status}): ${msg}`);
  }
  const json = r.data || {};
  if (!json || !json.task_id) {
    throw new Error('Upload response missing task_id');
  }
  return { taskId: json.task_id, originalFilename: json.original_filename || path.basename(filePath) };
}

async function pollTaskAndHandleDownload(event, baseUrl, taskId, originalFilename) {
  const sender = event.sender;
  const progressChannel = 'pdf:progress';
  const doneChannel = 'pdf:done';
  const errorChannel = 'pdf:error';

  const statusPath = `/task_status/${encodeURIComponent(taskId)}`;
  const downloadPath = `/download_highlighted_pdf/${encodeURIComponent(taskId)}`;

  const intervalMs = 1000;
  const maxMinutes = 30;
  const deadline = Date.now() + maxMinutes * 60 * 1000;

  while (true) {
    if (Date.now() > deadline) {
      try { sender.send(errorChannel, { taskId, error: 'timeout' }); } catch (_) {}
      return;
    }
    const taskState = activeTasks.get(taskId);
    if (!taskState || taskState.stop) {
      // Cancelled
      try { sender.send(errorChannel, { taskId, error: 'cancelled' }); } catch (_) {}
      return;
    }
    try {
      const r = await apiClient.request(statusPath, { method: 'GET', timeoutMs: 10000 });
      if (!r || !r.ok) {
        throw new Error((r && (r.message || (r.data && (r.data.error || r.data.message)))) || 'status_error');
      }
      const json = r.data || {};
      const state = json && json.state ? String(json.state) : 'UNKNOWN';
      const meta = (json && json.meta) || {};
      const statusMessage = (json && json.status_message) || state;
      try { sender.send(progressChannel, { taskId, state, meta, statusMessage }); } catch (_) {}

      if (state === 'SUCCESS') {
        // Download result
        const saveDefault = (json && json.result && json.result.highlighted_pdf_filename) ? json.result.highlighted_pdf_filename : (originalFilename || 'result.pdf');
        const { canceled, filePath: outPath } = await dialog.showSaveDialog({
          title: 'Save highlighted PDF',
          defaultPath: saveDefault,
          filters: [{ name: 'PDF Files', extensions: ['pdf'] }],
        });
        if (!canceled && outPath) {
          const dr = await apiClient.request(downloadPath, { method: 'GET', responseType: 'arrayBuffer', timeoutMs: 60000 });
          if (!dr || !dr.ok) {
            try { sender.send(errorChannel, { taskId, error: `download_failed_${dr && dr.status ? dr.status : '0'}` }); } catch (_) {}
            activeTasks.delete(taskId);
            return;
          }
          const arrayBuf = dr.data;
          await fs.promises.writeFile(outPath, Buffer.from(arrayBuf));
          try { sender.send(doneChannel, { taskId, savedPath: outPath }); } catch (_) {}
        } else {
          try { sender.send(doneChannel, { taskId, savedPath: null, canceled: true }); } catch (_) {}
        }
        activeTasks.delete(taskId);
        return;
      }
      if (state === 'FAILURE' || state === 'REVOKED') {
        const err = (json && (json.error || json.error_details)) || 'failed';
        try { sender.send(errorChannel, { taskId, error: String(err) }); } catch (_) {}
        activeTasks.delete(taskId);
        return;
      }
    } catch (e) {
      try { sender.send(errorChannel, { taskId, error: e && e.message ? e.message : String(e) }); } catch (_) {}
      activeTasks.delete(taskId);
      return;
    }
    // Wait
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

// IPC: process a PDF (renderer -> main)
ipcMain.handle('pdf:process', async (event, { filePath, options } = {}) => {
  try {
    if (!isPdfPath(filePath)) {
      throw new Error('Invalid PDF path');
    }
    const baseUrl = await resolveBackendBaseUrl();
    const { taskId, originalFilename } = await uploadPdfAndGetTaskId(baseUrl, filePath, options || {});
    activeTasks.set(taskId, { stop: false, webContentsId: event.sender.id });
    // detach polling, stream progress via events
    pollTaskAndHandleDownload(event, baseUrl, taskId, originalFilename).catch((e) => {
      try { event.sender.send('pdf:error', { taskId, error: e && e.message ? e.message : String(e) }); } catch (_) {}
      activeTasks.delete(taskId);
    });
    return { ok: true, taskId };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
});

// IPC: cancel a PDF task (best-effort)
ipcMain.handle('pdf:cancel', async (_event, { taskId } = {}) => {
  try {
    if (!taskId) return { ok: false, error: 'missing_taskId' };
    const state = activeTasks.get(taskId);
    if (state) state.stop = true;
    const r = await apiClient.request('/cancel_pdf_task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId }),
      timeoutMs: 8000,
    });
    const json = (r && r.ok && r.data) ? r.data : {};
    return { ok: Boolean(r && r.ok), cancelled: Boolean(json && json.cancelled), error: r && !r.ok ? (r.message || (json && (json.error || json.message)) || 'cancel_failed') : null };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
});
