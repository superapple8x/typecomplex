// Secure preload running in isolated context.
// Exposes a minimal, validated API surface to the renderer.

const { contextBridge, ipcRenderer } = require('electron');

function safeInvoke(channel, payload) {
  return ipcRenderer.invoke(channel, payload);
}

contextBridge.exposeInMainWorld('api', {
  healthCheck: async () => {
    const result = await safeInvoke('health:check');
    return result;
  },
  selectPdf: async () => {
    const filePath = await safeInvoke('file:openPdf');
    return filePath || null;
  },
  processPdf: async (filePath, options = {}) => {
    const res = await safeInvoke('pdf:process', { filePath, options });
    return res;
  },
  cancelPdf: async (taskId) => {
    const res = await safeInvoke('pdf:cancel', { taskId });
    return res;
  },
  onPdfProgress: (listener) => {
    if (typeof listener !== 'function') return () => {};
    const ch = 'pdf:progress';
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on(ch, handler);
    return () => ipcRenderer.removeListener(ch, handler);
  },
  onPdfDone: (listener) => {
    if (typeof listener !== 'function') return () => {};
    const ch = 'pdf:done';
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on(ch, handler);
    return () => ipcRenderer.removeListener(ch, handler);
  },
  onPdfError: (listener) => {
    if (typeof listener !== 'function') return () => {};
    const ch = 'pdf:error';
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on(ch, handler);
    return () => ipcRenderer.removeListener(ch, handler);
  },
});

// Optional lightweight logging to help early dev diagnostics
try {
  window.addEventListener('DOMContentLoaded', () => {
    try { console.log('[preload] DOMContentLoaded'); } catch (_) {}
  });
} catch (_) {}
