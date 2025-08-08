
const { app, BrowserWindow } = require('electron');
const path = require('path');
const { PythonProcessManager } = require('./pythonProcessManager');
// const http = require('http');

let processManager = null;
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
  });

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
    if (mainWindow) {
      await mainWindow.loadURL(url);
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
  // Disable GPU to avoid EGL/ANGLE issues on some Linux setups
  app.commandLine.appendSwitch('disable-gpu');
  app.commandLine.appendSwitch('disable-software-rasterizer');

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
