const path = require('path');
const { app } = require('electron');

// Resolve proper constructor for electron-store with fallback
let StoreCtor;
class NoopStore {
  constructor(opts = {}) { this.data = { ...(opts.defaults || {}) }; }
  get(k, d) { return this.data[k] ?? d; }
  set(k, v) { this.data[k] = v; }
  delete(k) { delete this.data[k]; }
  clear() { this.data = {}; }
  get store() { return this.data; }
}
try {
  const mod = require('electron-store');
  StoreCtor = (mod && typeof mod === 'object' && typeof mod.default === 'function') ? mod.default : mod;
} catch (_) {
  StoreCtor = NoopStore;
}

const DEFAULTS = {
  targetAudience: 'Standard', // 'Standard' | 'General Public' | 'Academic / Technical'
  analysisMode: 'better',     // 'fast' | 'better' | 'best'
  deepseekKeyStatus: 'unset', // 'unset' | 'set' (status only; never the key)
  modelCache: true,
  autoUpdate: true,
};

// Use a separate store file from process-state; keep secrets out
let settingsStore;
try {
  settingsStore = new StoreCtor({ name: 'settings', defaults: DEFAULTS });
} catch (_) {
  settingsStore = new NoopStore({ defaults: DEFAULTS });
}

function getPrefs() {
  return {
    targetAudience: settingsStore.get('targetAudience', DEFAULTS.targetAudience),
    analysisMode: settingsStore.get('analysisMode', DEFAULTS.analysisMode),
    deepseekKeyStatus: settingsStore.get('deepseekKeyStatus', DEFAULTS.deepseekKeyStatus),
    modelCache: settingsStore.get('modelCache', DEFAULTS.modelCache),
    autoUpdate: settingsStore.get('autoUpdate', DEFAULTS.autoUpdate),
  };
}

function setPrefs(partial) {
  if (!partial || typeof partial !== 'object') return getPrefs();
  const next = { ...getPrefs() };
  if (typeof partial.targetAudience === 'string' && ['Standard', 'General Public', 'Academic / Technical'].includes(partial.targetAudience)) {
    next.targetAudience = partial.targetAudience;
  }
  if (typeof partial.analysisMode === 'string' && ['fast', 'better', 'best'].includes(partial.analysisMode)) {
    next.analysisMode = partial.analysisMode;
  }
  if (typeof partial.modelCache === 'boolean') {
    next.modelCache = partial.modelCache;
  }
  if (typeof partial.autoUpdate === 'boolean') {
    next.autoUpdate = partial.autoUpdate;
  }
  // deepseekKeyStatus is maintained by backend status checks; but allow explicit status updates from main handlers
  if (typeof partial.deepseekKeyStatus === 'string' && ['unset', 'set'].includes(partial.deepseekKeyStatus)) {
    next.deepseekKeyStatus = partial.deepseekKeyStatus;
  }
  for (const [k, v] of Object.entries(next)) settingsStore.set(k, v);
  return next;
}

function resetPrefs() {
  for (const key of Object.keys(DEFAULTS)) settingsStore.set(key, DEFAULTS[key]);
  return getPrefs();
}

module.exports = { getPrefs, setPrefs, resetPrefs };