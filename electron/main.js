
const { app, BrowserWindow, Notification, dialog } = require('electron');

// Disable GPU and hardware acceleration early to avoid EGL/ANGLE issues on Linux
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
// Removed to allow software rasterizer fallback to work properly
// app.commandLine.appendSwitch('disable-software-rasterizer');
app.commandLine.appendSwitch('disable-webgpu');
app.commandLine.appendSwitch('use-gl', 'swiftshader');
app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
const path = require('path');
const { PythonProcessManager } = require('./pythonProcessManager');
const { store, getUserDataPath } = require('./store');
const http = require('http');

let processManager = null;
let pendingBackendUrl = null;
let triedAlternateHost = false;
let mainWindow = null;
// Managed by PythonProcessManager

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
      webgl: false, // reduce GPU use in renderer
      webviewTag: true, // allow webview wrapper fallback in dev
    },
    backgroundColor: '#ffffff',
    show: true,
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

  // If backend already ready, load immediately
  if (pendingBackendUrl) {
    mainWindow.loadURL(pendingBackendUrl).catch((e) => console.error('Initial load failed:', e));
  }

  // Will load the URL after healthcheck passes
  // Periodically log current URL for a short window
  let urlLogCount = 0;
  const urlLogger = setInterval(() => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      clearInterval(urlLogger);
      return;
    }
    urlLogCount += 1;
    console.log('current webContents URL:', mainWindow.webContents.getURL());
    if (urlLogCount >= 15) {
      clearInterval(urlLogger);
    }
  }, 1000);

  // Ensure we render something immediately while backend warms up
  if (!pendingBackendUrl) {
    mainWindow.loadURL('data:text/html,<h2>Starting backend…</h2><p>Please wait…</p>');
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
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
    if (mainWindow) {
      try {
        await mainWindow.loadURL(url);
      } catch (e) {
        console.error('Load failed on ready:', e);
      }
      // Double-check after a short delay; retry with localhost if needed
      setTimeout(async () => {
        try {
          const current = mainWindow.webContents.getURL();
          if (!current || current.startsWith('data:text/html')) {
            const alt = url.replace('127.0.0.1', 'localhost');
            console.warn('Retrying navigation to backend (alt host)...');
            await mainWindow.loadURL(alt);
            // If still on data: after another delay, try webview wrapper as fallback
            setTimeout(async () => {
              const afterAlt = mainWindow.webContents.getURL();
              if (!afterAlt || afterAlt.startsWith('data:text/html')) {
                console.warn('Falling back to webview wrapper for navigation');
                try {
                  await mainWindow.loadURL(buildWebviewWrapperDataUrl(url));
                } catch (fallbackErr) {
                  console.error('Webview wrapper load error:', fallbackErr);
                }
              }
            }, 1500);
          }
        } catch (err) {
          console.error('Retry load error:', err);
        }
      }, 1500);
    }
  });

  // If backend reports unhealthy before ready, show a temporary page instead of blank
  processManager.on('unhealthy', () => {
    if (mainWindow && !pendingBackendUrl) {
      mainWindow.loadURL('data:text/html,<h2>Starting backend…</h2><p>Please wait…</p>');
    }
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
  // Also start a main-process health poller to navigate once ready in case we miss the event
  pollHealthAndNavigate();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
      if (processManager) {
    processManager.stop().finally(() => app.quit());
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
  if (processManager) {
    processManager.stop();
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
