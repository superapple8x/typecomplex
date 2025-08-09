const assert = require('assert');
const proxyquire = require('proxyquire');

function makeElectronStub() {
  const ipcMain = { handle: () => {} };
  const app = {
    getPath: () => process.cwd(),
    disableHardwareAcceleration: () => {},
    commandLine: { appendSwitch: () => {} },
    on: () => {},
  };
  return { electron: { app, ipcMain } };
}

(async () => {
  const { electron } = makeElectronStub();
  class InMemoryStore {
    constructor(opts = {}) { this.data = { ...(opts.defaults || {}) }; }
    get(k, d) { return this.data[k] ?? d; }
    set(k, v) { this.data[k] = v; }
    delete(k) { delete this.data[k]; }
    clear() { this.data = {}; }
    get store() { return this.data; }
  }

  const settingsModule = proxyquire('../settingsStore', {
    electron,
    'electron-store': InMemoryStore,
  });

  settingsModule.migrateIfNeeded();
  // Change some prefs
  settingsModule.setPrefs({ targetAudience: 'General Public', analysisMode: 'fast', modelCache: false, autoUpdate: false });
  const prefs = settingsModule.getPrefs();
  const exported = settingsModule.exportPrefs();
  assert.ok(exported && exported.preferences, 'export should include preferences');
  assert.strictEqual(exported.preferences.targetAudience, prefs.targetAudience);

  // Import into a new store instance and verify
  const settingsModule2 = proxyquire('../settingsStore', {
    electron,
    'electron-store': InMemoryStore,
  });
  settingsModule2.migrateIfNeeded();
  const imported = settingsModule2.importPrefs(exported);
  assert.strictEqual(imported.targetAudience, prefs.targetAudience);
  assert.strictEqual(imported.analysisMode, prefs.analysisMode);
  assert.strictEqual(imported.modelCache, prefs.modelCache);
  assert.strictEqual(imported.autoUpdate, prefs.autoUpdate);

  // Ensure schema version set to latest after import
  assert.strictEqual(settingsModule2.getSchemaVersion(), settingsModule2.SETTINGS_SCHEMA_VERSION);

  // Invalid payload should not crash and should return current prefs
  const afterInvalid = settingsModule2.importPrefs(null);
  assert.ok(afterInvalid && typeof afterInvalid === 'object');

  console.log('OK: settings export/import');
})().catch((err) => { console.error('TEST FAILURE:', err); process.exit(1); });


