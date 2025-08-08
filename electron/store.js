const path = require('path');
const { app } = require('electron');
let Store;
try {
  // Lazy require to avoid hard crash if not installed yet
  Store = require('electron-store');
} catch (_) {
  // Minimal shim: noop store in case dependency missing during dev
  class NoopStore {
    constructor() { this.data = {}; }
    get(k, d) { return this.data[k] ?? d; }
    set(k, v) { this.data[k] = v; }
    delete(k) { delete this.data[k]; }
  }
  Store = NoopStore;
}

const store = new Store({
  name: 'process-state',
});

function getUserDataPath() {
  try {
    return app.getPath('userData');
  } catch (_) {
    return path.join(process.cwd(), '.userData');
  }
}

module.exports = { store, getUserDataPath };
