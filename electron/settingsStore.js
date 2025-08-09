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

// Settings schema versioning
const SETTINGS_SCHEMA_VERSION = 1;
const TARGET_AUDIENCE_VALUES = ['Standard', 'General Public', 'Academic / Technical'];
const ANALYSIS_MODE_VALUES = ['fast', 'better', 'best'];
const KEY_STATUS_VALUES = ['unset', 'set'];

// Use a separate store file from process-state; keep secrets out
let settingsStore;
try {
  settingsStore = new StoreCtor({ name: 'settings', defaults: DEFAULTS });
} catch (_) {
  settingsStore = new NoopStore({ defaults: DEFAULTS });
}

function sanitizePrefs(input) {
  const out = { ...DEFAULTS };
  const ta = input && typeof input.targetAudience === 'string' ? input.targetAudience : DEFAULTS.targetAudience;
  out.targetAudience = TARGET_AUDIENCE_VALUES.includes(ta) ? ta : DEFAULTS.targetAudience;

  const am = input && typeof input.analysisMode === 'string' ? input.analysisMode : DEFAULTS.analysisMode;
  out.analysisMode = ANALYSIS_MODE_VALUES.includes(am) ? am : DEFAULTS.analysisMode;

  const ks = input && typeof input.deepseekKeyStatus === 'string' ? input.deepseekKeyStatus : DEFAULTS.deepseekKeyStatus;
  out.deepseekKeyStatus = KEY_STATUS_VALUES.includes(ks) ? ks : DEFAULTS.deepseekKeyStatus;

  out.modelCache = Boolean(input && typeof input.modelCache === 'boolean' ? input.modelCache : DEFAULTS.modelCache);
  out.autoUpdate = Boolean(input && typeof input.autoUpdate === 'boolean' ? input.autoUpdate : DEFAULTS.autoUpdate);

  return out;
}

function getPrefs() {
  const current = {
    targetAudience: settingsStore.get('targetAudience', DEFAULTS.targetAudience),
    analysisMode: settingsStore.get('analysisMode', DEFAULTS.analysisMode),
    deepseekKeyStatus: settingsStore.get('deepseekKeyStatus', DEFAULTS.deepseekKeyStatus),
    modelCache: settingsStore.get('modelCache', DEFAULTS.modelCache),
    autoUpdate: settingsStore.get('autoUpdate', DEFAULTS.autoUpdate),
  };
  return sanitizePrefs(current);
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
  settingsStore.set('schemaVersion', SETTINGS_SCHEMA_VERSION);
  return getPrefs();
}

function getSchemaVersion() {
  try {
    const v = settingsStore.get('schemaVersion', 0);
    return Number.isFinite(v) ? Number(v) : 0;
  } catch (_) {
    return 0;
  }
}

// Migration steps by from-version
const migrations = {
  // v0 -> v1: introduce schemaVersion; ensure keys exist and sanitize values
  0: () => {
    const sanitized = sanitizePrefs({
      targetAudience: settingsStore.get('targetAudience', DEFAULTS.targetAudience),
      analysisMode: settingsStore.get('analysisMode', DEFAULTS.analysisMode),
      deepseekKeyStatus: settingsStore.get('deepseekKeyStatus', DEFAULTS.deepseekKeyStatus),
      modelCache: settingsStore.get('modelCache', DEFAULTS.modelCache),
      autoUpdate: settingsStore.get('autoUpdate', DEFAULTS.autoUpdate),
    });
    for (const [k, v] of Object.entries(sanitized)) settingsStore.set(k, v);
    settingsStore.set('schemaVersion', 1);
  },
};

function migrateIfNeeded() {
  try {
    let current = getSchemaVersion();
    if (!Number.isFinite(current)) current = 0;
    while (current < SETTINGS_SCHEMA_VERSION) {
      const step = migrations[current];
      if (typeof step === 'function') {
        step();
      } else {
        // If no explicit step, just bump to target
        settingsStore.set('schemaVersion', SETTINGS_SCHEMA_VERSION);
        break;
      }
      current = getSchemaVersion();
      if (current <= 0) {
        // Ensure progress; avoid infinite loop on broken stores
        current = SETTINGS_SCHEMA_VERSION;
        settingsStore.set('schemaVersion', SETTINGS_SCHEMA_VERSION);
      }
    }
    // Final sanity write of schema version
    settingsStore.set('schemaVersion', SETTINGS_SCHEMA_VERSION);
  } catch (e) {
    // Recovery: reset to defaults with current schema
    for (const key of Object.keys(DEFAULTS)) settingsStore.set(key, DEFAULTS[key]);
    settingsStore.set('schemaVersion', SETTINGS_SCHEMA_VERSION);
  }
}

function exportPrefs() {
  const prefs = getPrefs();
  return {
    schemaVersion: SETTINGS_SCHEMA_VERSION,
    preferences: prefs,
  };
}

function importPrefs(payload) {
  try {
    const obj = (payload && typeof payload === 'object') ? payload : {};
    const incoming = obj.preferences && typeof obj.preferences === 'object' ? obj.preferences : obj; // accept bare prefs or wrapped
    const sanitized = sanitizePrefs(incoming);
    for (const [k, v] of Object.entries(sanitized)) settingsStore.set(k, v);
    // Always set current schema version regardless of incoming
    settingsStore.set('schemaVersion', SETTINGS_SCHEMA_VERSION);
    return getPrefs();
  } catch (_) {
    return getPrefs();
  }
}

module.exports = { getPrefs, setPrefs, resetPrefs, getSchemaVersion, migrateIfNeeded, SETTINGS_SCHEMA_VERSION, exportPrefs, importPrefs };