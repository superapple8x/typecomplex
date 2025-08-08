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
});

// Optional lightweight logging to help early dev diagnostics
try {
  window.addEventListener('DOMContentLoaded', () => {
    try { console.log('[preload] DOMContentLoaded'); } catch (_) {}
  });
} catch (_) {}
