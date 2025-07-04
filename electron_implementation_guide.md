# TypeComplex Electron Implementation Guide

## Project Structure

```
typecomplex-electron/
├── package.json
├── main.js                    # Electron main process
├── preload.js                 # Preload script for security
├── electron-builder.yml       # Build configuration
├── python_backend/            # Modified Flask backend
│   ├── app/
│   ├── requirements.txt
│   └── run_desktop.py         # Desktop-specific runner
├── renderer/                  # Frontend files
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── api/
├── services/                  # Electron services
│   ├── pythonService.js
│   ├── modelManager.js
│   └── fileHandler.js
└── resources/                 # App resources
    ├── icons/
    └── models/                # Pre-downloaded NLP models

```

## 1. Main Process Implementation

### main.js
```javascript
const { app, BrowserWindow, ipcMain, dialog, Menu, Tray, nativeImage } = require('electron');
const path = require('path');
const PythonService = require('./services/pythonService');
const ModelManager = require('./services/modelManager');
const FileHandler = require('./services/fileHandler');
const { autoUpdater } = require('electron-updater');

// Keep a global reference of the window object
let mainWindow;
let pythonService;
let modelManager;
let fileHandler;
let tray;

// Enable live reload for Electron too
if (process.env.NODE_ENV === 'development') {
  require('electron-reload')(__dirname, {
    electron: path.join(__dirname, '..', 'node_modules', '.bin', 'electron'),
    hardResetMethod: 'exit'
  });
}

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // Someone tried to run a second instance, focus our window instead
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  // Create window
  function createWindow() {
    mainWindow = new BrowserWindow({
      width: 1400,
      height: 900,
      minWidth: 1200,
      minHeight: 700,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, 'preload.js')
      },
      icon: path.join(__dirname, 'resources/icons/icon.png'),
      titleBarStyle: 'hiddenInset',
      backgroundColor: '#1f2028'
    });

    mainWindow.loadFile('renderer/index.html');

    // Open DevTools in development
    if (process.env.NODE_ENV === 'development') {
      mainWindow.webContents.openDevTools();
    }

    mainWindow.on('closed', () => {
      mainWindow = null;
    });

    // Handle window close to tray
    mainWindow.on('close', (event) => {
      if (!app.isQuitting) {
        event.preventDefault();
        mainWindow.hide();
      }
    });
  }

  // Application menu
  function createMenu() {
    const template = [
      {
        label: 'File',
        submenu: [
          {
            label: 'Open PDF',
            accelerator: 'CmdOrCtrl+O',
            click: async () => {
              const result = await fileHandler.openPDFDialog();
              if (result) {
                mainWindow.webContents.send('pdf-opened', result);
              }
            }
          },
          {
            label: 'Save Analysis',
            accelerator: 'CmdOrCtrl+S',
            click: () => {
              mainWindow.webContents.send('save-analysis');
            }
          },
          { type: 'separator' },
          { role: 'quit' }
        ]
      },
      {
        label: 'Edit',
        submenu: [
          { role: 'undo' },
          { role: 'redo' },
          { type: 'separator' },
          { role: 'cut' },
          { role: 'copy' },
          { role: 'paste' }
        ]
      },
      {
        label: 'View',
        submenu: [
          { role: 'reload' },
          { role: 'forceReload' },
          { role: 'toggleDevTools' },
          { type: 'separator' },
          { role: 'resetZoom' },
          { role: 'zoomIn' },
          { role: 'zoomOut' }
        ]
      }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
  }

  // System tray
  function createTray() {
    const icon = nativeImage.createFromPath(
      path.join(__dirname, 'resources/icons/tray-icon.png')
    );
    
    tray = new Tray(icon);
    
    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Show TypeComplex',
        click: () => {
          mainWindow.show();
        }
      },
      {
        label: 'Quit',
        click: () => {
          app.isQuitting = true;
          app.quit();
        }
      }
    ]);
    
    tray.setToolTip('TypeComplex');
    tray.setContextMenu(contextMenu);
    
    tray.on('click', () => {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    });
  }

  // App ready
  app.whenReady().then(async () => {
    // Initialize services
    pythonService = new PythonService();
    modelManager = new ModelManager();
    fileHandler = new FileHandler();

    // Start Python backend
    try {
      await pythonService.start();
      console.log('Python backend started successfully');
    } catch (error) {
      console.error('Failed to start Python backend:', error);
      dialog.showErrorBox('Startup Error', 
        'Failed to start the analysis service. Please restart the application.');
    }

    // Check and download models if needed
    await modelManager.ensureModelsAvailable();

    createWindow();
    createMenu();
    createTray();

    // Auto-updater
    autoUpdater.checkForUpdatesAndNotify();
  });

  // Quit when all windows are closed
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      app.quit();
    }
  });

  app.on('activate', () => {
    if (mainWindow === null) {
      createWindow();
    }
  });

  // Cleanup on quit
  app.on('before-quit', async () => {
    if (pythonService) {
      await pythonService.stop();
    }
  });
}

// IPC Handlers
ipcMain.handle('analyze-text', async (event, data) => {
  return await pythonService.analyzeText(data);
});

ipcMain.handle('get-synonyms', async (event, data) => {
  return await pythonService.getSynonyms(data);
});

ipcMain.handle('open-pdf', async () => {
  return await fileHandler.openPDFDialog();
});

ipcMain.handle('save-file', async (event, data) => {
  return await fileHandler.saveFile(data);
});

ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

ipcMain.handle('check-model-status', async () => {
  return await modelManager.checkModelStatus();
});
```

### preload.js
```javascript
const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process
// to communicate with the main process
contextBridge.exposeInMainWorld('electronAPI', {
  // Analysis functions
  analyzeText: (data) => ipcRenderer.invoke('analyze-text', data),
  getSynonyms: (data) => ipcRenderer.invoke('get-synonyms', data),
  
  // File operations
  openPDF: () => ipcRenderer.invoke('open-pdf'),
  saveFile: (data) => ipcRenderer.invoke('save-file', data),
  
  // App info
  getVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // Model management
  checkModelStatus: () => ipcRenderer.invoke('check-model-status'),
  
  // Event listeners
  onPDFOpened: (callback) => ipcRenderer.on('pdf-opened', callback),
  onSaveAnalysis: (callback) => ipcRenderer.on('save-analysis', callback),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});
```

## 2. Service Layer Implementation

### services/pythonService.js
```javascript
const { spawn } = require('child_process');
const path = require('path');
const axios = require('axios');
const waitOn = require('wait-on');
const { app } = require('electron');

class PythonService {
  constructor() {
    this.flaskProcess = null;
    this.celeryProcess = null;
    this.redisProcess = null;
    this.baseURL = 'http://localhost:5001';
    this.isRunning = false;
  }

  async start() {
    // Determine Python executable path
    const isProd = app.isPackaged;
    const pythonPath = isProd 
      ? path.join(process.resourcesPath, 'python', 'python')
      : 'python3';

    const backendPath = isProd
      ? path.join(process.resourcesPath, 'python_backend')
      : path.join(__dirname, '..', 'python_backend');

    // Start Redis (embedded)
    this.redisProcess = spawn(
      isProd ? path.join(process.resourcesPath, 'redis', 'redis-server') : 'redis-server',
      ['--port', '6379', '--save', '""', '--appendonly', 'no'],
      { stdio: 'pipe' }
    );

    // Wait for Redis to start
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Start Flask server
    this.flaskProcess = spawn(pythonPath, [path.join(backendPath, 'run_desktop.py')], {
      cwd: backendPath,
      env: {
        ...process.env,
        FLASK_APP: 'app:app',
        FLASK_ENV: 'desktop',
        DESKTOP_MODE: 'true',
        PYTHONPATH: backendPath
      },
      stdio: ['pipe', 'pipe', 'pipe']
    });

    // Log Flask output
    this.flaskProcess.stdout.on('data', (data) => {
      console.log(`Flask: ${data}`);
    });

    this.flaskProcess.stderr.on('data', (data) => {
      console.error(`Flask Error: ${data}`);
    });

    // Start Celery worker
    this.celeryProcess = spawn(
      pythonPath,
      ['-m', 'celery', '-A', 'app.celery', 'worker', '--loglevel=info', '--concurrency=2'],
      {
        cwd: backendPath,
        env: {
          ...process.env,
          PYTHONPATH: backendPath
        },
        stdio: 'pipe'
      }
    );

    // Wait for Flask to be ready
    await waitOn({
      resources: [`${this.baseURL}/health`],
      timeout: 30000,
      interval: 1000
    });

    this.isRunning = true;
  }

  async stop() {
    const processes = [this.flaskProcess, this.celeryProcess, this.redisProcess];
    
    for (const proc of processes) {
      if (proc && !proc.killed) {
        proc.kill('SIGTERM');
        await new Promise(resolve => {
          proc.on('exit', resolve);
          setTimeout(resolve, 5000); // Timeout after 5 seconds
        });
      }
    }
    
    this.isRunning = false;
  }

  async analyzeText(data) {
    if (!this.isRunning) {
      throw new Error('Python service is not running');
    }

    try {
      const response = await axios.post(`${this.baseURL}/analyze`, data, {
        headers: { 'Content-Type': 'application/json' }
      });
      return response.data;
    } catch (error) {
      console.error('Analysis error:', error);
      throw error;
    }
  }

  async getSynonyms(data) {
    if (!this.isRunning) {
      throw new Error('Python service is not running');
    }

    try {
      const response = await axios.post(`${this.baseURL}/synonyms`, data, {
        headers: { 'Content-Type': 'application/json' }
      });
      return response.data;
    } catch (error) {
      console.error('Synonyms error:', error);
      throw error;
    }
  }
}

module.exports = PythonService;
```

### services/modelManager.js
```javascript
const path = require('path');
const fs = require('fs-extra');
const axios = require('axios');
const { app, dialog } = require('electron');
const AdmZip = require('adm-zip');

class ModelManager {
  constructor() {
    this.modelsPath = path.join(app.getPath('userData'), 'models');
    this.requiredModels = [
      {
        name: 'en_core_web_sm',
        url: 'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.0/en_core_web_sm-3.7.0-py3-none-any.whl',
        size: '12MB'
      },
      {
        name: 'en_core_web_lg',
        url: 'https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.0/en_core_web_lg-3.7.0-py3-none-any.whl',
        size: '560MB'
      }
    ];
  }

  async ensureModelsAvailable() {
    await fs.ensureDir(this.modelsPath);
    
    for (const model of this.requiredModels) {
      const modelPath = path.join(this.modelsPath, model.name);
      
      if (!await fs.pathExists(modelPath)) {
        const download = await this.promptModelDownload(model);
        if (download) {
          await this.downloadModel(model);
        }
      }
    }
  }

  async promptModelDownload(model) {
    const result = await dialog.showMessageBox({
      type: 'question',
      buttons: ['Download', 'Skip'],
      defaultId: 0,
      title: 'Model Download Required',
      message: `The ${model.name} model (${model.size}) is required for analysis. Download now?`,
      detail: 'This is a one-time download. The model will be stored locally.'
    });
    
    return result.response === 0;
  }

  async downloadModel(model, progressCallback) {
    const modelPath = path.join(this.modelsPath, model.name);
    const tempPath = `${modelPath}.tmp`;
    
    try {
      const response = await axios({
        method: 'GET',
        url: model.url,
        responseType: 'stream',
        onDownloadProgress: (progressEvent) => {
          if (progressCallback) {
            const progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            progressCallback(progress);
          }
        }
      });
      
      const writer = fs.createWriteStream(tempPath);
      response.data.pipe(writer);
      
      await new Promise((resolve, reject) => {
        writer.on('finish', resolve);
        writer.on('error', reject);
      });
      
      // Extract if it's a wheel file
      if (model.url.endsWith('.whl')) {
        const zip = new AdmZip(tempPath);
        zip.extractAllTo(modelPath, true);
        await fs.remove(tempPath);
      } else {
        await fs.move(tempPath, modelPath);
      }
      
      return true;
    } catch (error) {
      console.error(`Failed to download model ${model.name}:`, error);
      await fs.remove(tempPath).catch(() => {});
      throw error;
    }
  }

  async checkModelStatus() {
    const status = {};
    
    for (const model of this.requiredModels) {
      const modelPath = path.join(this.modelsPath, model.name);
      status[model.name] = await fs.pathExists(modelPath);
    }
    
    return status;
  }
}

module.exports = ModelManager;
```

## 3. Renderer Process Implementation

### renderer/js/api.js
```javascript
// API wrapper for communication with backend
class TypeComplexAPI {
  constructor() {
    this.electronAPI = window.electronAPI;
  }

  async analyzeText(text, targetAudience = 'Standard', mode = 'better', analysisId = null) {
    try {
      const result = await this.electronAPI.analyzeText({
        text,
        target_audience: targetAudience,
        mode,
        analysisId,
        context_awareness_enabled: false
      });
      return result;
    } catch (error) {
      console.error('Analysis failed:', error);
      throw error;
    }
  }

  async getSynonyms(word, sentenceContext, targetAudience = 'Standard') {
    try {
      const result = await this.electronAPI.getSynonyms({
        word,
        sentence_context: sentenceContext,
        target_audience: targetAudience,
        context_awareness_enabled: false
      });
      return result;
    } catch (error) {
      console.error('Synonym lookup failed:', error);
      throw error;
    }
  }

  async openPDF() {
    try {
      const result = await this.electronAPI.openPDF();
      return result;
    } catch (error) {
      console.error('PDF open failed:', error);
      throw error;
    }
  }

  async saveAnalysis(data) {
    try {
      const result = await this.electronAPI.saveFile({
        type: 'analysis',
        data
      });
      return result;
    } catch (error) {
      console.error('Save failed:', error);
      throw error;
    }
  }
}

// Export for use in other modules
window.TypeComplexAPI = TypeComplexAPI;
```

### renderer/js/main.js
```javascript
// Main renderer process logic
document.addEventListener('DOMContentLoaded', async () => {
  const api = new TypeComplexAPI();
  
  // Initialize Quill editor
  const quill = new Quill('#editor-container', {
    theme: 'snow',
    modules: {
      toolbar: [
        ['bold', 'italic', 'underline'],
        ['blockquote', 'code-block'],
        [{ 'list': 'ordered'}, { 'list': 'bullet' }],
        ['clean']
      ]
    }
  });

  // Analysis button handler
  document.getElementById('analyze-btn').addEventListener('click', async () => {
    const text = quill.getText();
    const targetAudience = document.getElementById('target-audience').value;
    const mode = document.getElementById('analysis-mode').value;
    
    try {
      showLoadingState();
      const result = await api.analyzeText(text, targetAudience, mode);
      displayAnalysisResults(result);
    } catch (error) {
      showError('Analysis failed. Please try again.');
    } finally {
      hideLoadingState();
    }
  });

  // PDF handling
  window.electronAPI.onPDFOpened((event, pdfData) => {
    if (pdfData.text) {
      quill.setText(pdfData.text);
      showNotification('PDF loaded successfully');
    }
  });

  // Save handler
  window.electronAPI.onSaveAnalysis(async () => {
    const analysisData = gatherAnalysisData();
    if (analysisData) {
      try {
        await api.saveAnalysis(analysisData);
        showNotification('Analysis saved successfully');
      } catch (error) {
        showError('Failed to save analysis');
      }
    }
  });

  // Check model status on startup
  const modelStatus = await window.electronAPI.checkModelStatus();
  if (!modelStatus.en_core_web_sm || !modelStatus.en_core_web_lg) {
    showModelDownloadPrompt();
  }
});

// Helper functions
function showLoadingState() {
  document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoadingState() {
  document.getElementById('loading-overlay').classList.add('hidden');
}

function showNotification(message) {
  // Implementation for showing notifications
}

function showError(message) {
  // Implementation for showing errors
}

function displayAnalysisResults(results) {
  // Implementation for displaying results
}

function gatherAnalysisData() {
  // Implementation for gathering current analysis data
}
```

## 4. Backend Modifications

### python_backend/run_desktop.py
```python
#!/usr/bin/env python3
"""
Desktop runner for TypeComplex Flask application
"""
import os
import sys
from flask_cors import CORS

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

# Enable CORS for Electron renderer
CORS(app, origins=['http://localhost:*', 'file://*'])

# Desktop-specific configuration
app.config.update(
    DESKTOP_MODE=True,
    UPLOAD_FOLDER=os.path.join(os.path.expanduser('~'), 'TypeComplex', 'uploads'),
    PROCESSED_FOLDER=os.path.join(os.path.expanduser('~'), 'TypeComplex', 'processed'),
    RATE_LIMITING_ENABLED=False,  # Disable rate limiting for desktop
    CACHE_TYPE='FileSystemCache',
    CACHE_DIR=os.path.join(os.path.expanduser('~'), 'TypeComplex', 'cache')
)

# Ensure directories exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['PROCESSED_FOLDER'], app.config['CACHE_DIR']]:
    os.makedirs(folder, exist_ok=True)

# Add health check endpoint
@app.route('/health')
def health_check():
    return {'status': 'healthy', 'desktop_mode': True}

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)
```

## 5. Build Configuration

### package.json
```json
{
  "name": "typecomplex-desktop",
  "version": "1.0.0",
  "description": "TypeComplex Desktop - Sentence Complexity Analyzer",
  "main": "main.js",
  "scripts": {
    "start": "electron .",
    "dev": "NODE_ENV=development electron .",
    "build": "electron-builder",
    "build:win": "electron-builder --win",
    "build:mac": "electron-builder --mac",
    "build:linux": "electron-builder --linux",
    "pack": "electron-builder --dir",
    "dist": "electron-builder",
    "postinstall": "electron-builder install-app-deps"
  },
  "build": {
    "appId": "com.typecomplex.desktop",
    "productName": "TypeComplex",
    "directories": {
      "output": "dist"
    },
    "files": [
      "main.js",
      "preload.js",
      "renderer/**/*",
      "services/**/*",
      "resources/**/*",
      "python_backend/**/*",
      "!python_backend/__pycache__",
      "!python_backend/.env",
      "!python_backend/uploads",
      "!python_backend/processed_pdfs"
    ],
    "extraResources": [
      {
        "from": "python_dist",
        "to": "python"
      },
      {
        "from": "redis_dist",
        "to": "redis"
      }
    ],
    "mac": {
      "category": "public.app-category.productivity",
      "icon": "resources/icons/icon.icns",
      "hardenedRuntime": true,
      "entitlements": "build/entitlements.mac.plist",
      "entitlementsInherit": "build/entitlements.mac.plist",
      "gatekeeperAssess": false
    },
    "win": {
      "target": "nsis",
      "icon": "resources/icons/icon.ico"
    },
    "linux": {
      "target": "AppImage",
      "category": "Office",
      "icon": "resources/icons"
    },
    "nsis": {
      "oneClick": false,
      "allowToChangeInstallationDirectory": true
    }
  },
  "dependencies": {
    "axios": "^1.6.0",
    "electron-updater": "^6.1.0",
    "wait-on": "^7.0.0",
    "adm-zip": "^0.5.10",
    "fs-extra": "^11.0.0"
  },
  "devDependencies": {
    "electron": "^27.0.0",
    "electron-builder": "^24.6.0",
    "electron-reload": "^2.0.0-alpha.1"
  }
}
```

### electron-builder.yml
```yaml
appId: com.typecomplex.desktop
productName: TypeComplex
copyright: Copyright © 2024 TypeComplex

directories:
  buildResources: build
  output: dist

publish:
  provider: github
  owner: your-github-username
  repo: typecomplex-electron

mac:
  category: public.app-category.productivity
  hardenedRuntime: true
  gatekeeperAssess: false
  entitlements: build/entitlements.mac.plist
  entitlementsInherit: build/entitlements.mac.plist
  icon: resources/icons/icon.icns
  type: distribution
  target:
    - dmg
    - zip

win:
  icon: resources/icons/icon.ico
  publisherName: TypeComplex
  target:
    - nsis
    - portable

linux:
  category: Office
  icon: resources/icons
  target:
    - AppImage
    - deb
    - rpm

nsis:
  oneClick: false
  perMachine: false
  allowToChangeInstallationDirectory: true
  menuCategory: true
  installerIcon: resources/icons/icon.ico
  uninstallerIcon: resources/icons/icon.ico
  license: LICENSE

dmg:
  contents:
    - x: 110
      y: 150
    - x: 480
      y: 150
      type: link
      path: /Applications
```

## 6. Python Distribution Script

### scripts/build_python.sh
```bash
#!/bin/bash

# Build Python distribution for Electron app
echo "Building Python distribution..."

# Create virtual environment
python3 -m venv build_env
source build_env/bin/activate

# Install dependencies
pip install -r python_backend/requirements.txt
pip install pyinstaller

# Create spec file for PyInstaller
cat > typecomplex.spec << EOF
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['python_backend/run_desktop.py'],
    pathex=['python_backend'],
    binaries=[],
    datas=[
        ('python_backend/app', 'app'),
        ('python_backend/requirements.txt', '.'),
    ],
    hiddenimports=[
        'flask',
        'celery',
        'redis',
        'spacy',
        'nltk',
        'transformers',
        'torch',
        'textstat',
        'fitz',
        'app.routes',
        'app.analysis',
        'app.tasks',
        'app.deepseek_analysis',
        'app.gemini_analysis',
        'app.pdf_handler',
        'app.synonyms',
        'app.frequency',
        'app.rate_limiter',
        'app.task_manager'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='typecomplex_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='typecomplex_backend',
)
EOF

# Build with PyInstaller
pyinstaller typecomplex.spec

# Copy to distribution folder
mkdir -p python_dist
cp -r dist/typecomplex_backend/* python_dist/

# Download spaCy models
python -m spacy download en_core_web_sm
python -m spacy download en_core_web_lg

# Deactivate virtual environment
deactivate

echo "Python distribution built successfully!"
```

## Conclusion

This implementation guide provides the core structure and code needed to convert TypeComplex into an Electron desktop application. Key aspects include:

1. **Hybrid Architecture**: Maintains Python backend for NLP processing
2. **Service Management**: Robust process management for Python services
3. **Security**: Uses context isolation and preload scripts
4. **Cross-Platform**: Build configuration for Windows, macOS, and Linux
5. **User Experience**: Native file handling, system tray, auto-updates

The modular structure allows for incremental development and testing while maintaining the full feature set of the web application.