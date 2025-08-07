
const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let flaskProcess = null;
let mainWindow = null;
let restartAttempts = 0;
const maxRestartAttempts = 3;
const baseRestartDelayMs = 1000;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false, // Keep false for security
      contextIsolation: true, // Keep true for security
    },
  });

  // Will load the URL after healthcheck passes

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startFlask() {
  // Prefer running the Python entrypoint in dev; packaged binary can be set later
  const python = process.env.PYTHON_BINARY || 'python3';
  const serverPath = path.join(__dirname, '..', 'electron_server.py');
  const args = [serverPath, '--host', '127.0.0.1', '--port', '5001'];
  const env = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    ELECTRON_APP_PATH: path.join(__dirname, '..'),
  };
  flaskProcess = spawn(python, args, { env });

  flaskProcess.stdout.on('data', (data) => {
    console.log(`Flask stdout: ${data}`);
  });

  flaskProcess.stderr.on('data', (data) => {
    console.error(`Flask stderr: ${data}`);
  });

  flaskProcess.on('close', (code) => {
    console.log(`Flask process exited with code ${code}`);
    if (restartAttempts < maxRestartAttempts) {
      const delay = baseRestartDelayMs * Math.pow(2, restartAttempts);
      restartAttempts += 1;
      console.log(`Attempting to restart backend in ${delay}ms (attempt ${restartAttempts}/${maxRestartAttempts})`);
      setTimeout(async () => {
        startFlask();
        try {
          await waitForHealth('http://127.0.0.1:5001/health');
          if (mainWindow) {
            await mainWindow.loadURL('http://127.0.0.1:5001');
          }
        } catch (e) {
          console.error('Health check failed after restart attempt:', e);
        }
      }, delay);
    }
  });
  flaskProcess.on('error', (err) => {
    console.error('Flask process error:', err);
  });
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
  startFlask();
  createWindow();
  try {
    await waitForHealth('http://127.0.0.1:5001/health');
    if (mainWindow) {
      await mainWindow.loadURL('http://127.0.0.1:5001');
    }
  } catch (e) {
    console.error('Failed to reach Flask health endpoint:', e);
    if (mainWindow) {
      mainWindow.loadURL('data:text/html,<h1>Backend failed to start</h1>');
    }
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (flaskProcess) {
      console.log('Killing Flask process...');
      flaskProcess.kill();
    }
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

app.on('before-quit', () => {
  if (flaskProcess) {
    console.log('Killing Flask process before quit...');
    flaskProcess.kill();
  }
});
