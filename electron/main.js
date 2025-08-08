
const { app, BrowserWindow } = require('electron');

// Disable GPU and hardware acceleration early to avoid EGL/ANGLE issues on Linux
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.commandLine.appendSwitch('disable-webgpu');
app.commandLine.appendSwitch('use-gl', 'swiftshader');
app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
const path = require('path');
const { PythonProcessManager } = require('./pythonProcessManager');
// const http = require('http');

let processManager = null;
let pendingBackendUrl = null;
let triedAlternateHost = false;
let mainWindow = null;
// Managed by PythonProcessManager

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false, // Keep false for security
      contextIsolation: true, // Keep true for security
      webgl: false, // reduce GPU use in renderer
    },
    backgroundColor: '#ffffff',
    show: true,
  });

  // Debug load events to diagnose white screen
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

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startBackend() {
  // Prefer running the Python entrypoint in dev; packaged binary can be set later
  processManager = new PythonProcessManager({});

  processManager.on('stdout', (msg) => console.log(`Flask stdout: ${msg}`));
  processManager.on('stderr', (msg) => console.error(`Flask stderr: ${msg}`));
  processManager.on('ready', async ({ url }) => {
    console.log('Backend ready at', url);
    pendingBackendUrl = url;
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
  processManager.on('restarting', ({ attempt, delay }) => {
    console.log(`Attempting to restart backend in ${delay}ms (attempt ${attempt}/${processManager.maxRestartAttempts})`);
  });
  processManager.on('heartbeat-restart', () => {
    console.warn('Heartbeat: restarting Flask backend due to repeated health failures...');
  });
  processManager.on('failed', ({ message }) => {
    console.error(`Backend failed permanently: ${message}`);
    if (mainWindow) {
      mainWindow.loadURL('data:text/html,<h1>Backend failed to start</h1>');
    }
  });
  processManager.on('error', (err) => console.error('Flask process error:', err));

  processManager.start();
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

app.on('ready', async () => {
  startBackend();
  createWindow();
  // Health is now handled by PythonProcessManager events; no extra loop here.
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
