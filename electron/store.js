const path = require('path');
const { app } = require('electron');

// Robust Store constructor resolution with safe fallback for tests
let StoreCtor;
class NoopStore {
  constructor() { this.data = {}; }
  get(k, d) { return this.data[k] ?? d; }
  set(k, v) { this.data[k] = v; }
  delete(k) { delete this.data[k]; }
}
try {
  // Lazy require to avoid hard crash if not installed yet
  const mod = require('electron-store');
  StoreCtor = (mod && typeof mod === 'object' && typeof mod.default === 'function') ? mod.default : mod;
} catch (_) {
  StoreCtor = NoopStore;
}

let store;
try {
  store = new StoreCtor({ name: 'process-state' });
} catch (_) {
  // In some non-Electron test environments, electron-store may throw; fallback
  StoreCtor = NoopStore;
  store = new StoreCtor();
}

function getUserDataPath() {
  try {
    return app.getPath('userData');
  } catch (_) {
    return path.join(process.cwd(), '.userData');
  }
}

module.exports = { store, getUserDataPath };
