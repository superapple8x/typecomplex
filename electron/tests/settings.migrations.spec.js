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

  // Stub electron-store in-memory to avoid disk IO and isolate between tests
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

  // Fresh store should migrate to latest and include defaults
  settingsModule.migrateIfNeeded();
  const v = settingsModule.getSchemaVersion();
  assert.strictEqual(v, settingsModule.SETTINGS_SCHEMA_VERSION, 'schema version after migrate should equal latest');
  const prefs = settingsModule.getPrefs();
  assert.strictEqual(prefs.targetAudience, 'Standard');
  assert.strictEqual(prefs.analysisMode, 'better');
  assert.strictEqual(prefs.deepseekKeyStatus, 'unset');
  assert.strictEqual(typeof prefs.modelCache, 'boolean');
  assert.strictEqual(typeof prefs.autoUpdate, 'boolean');

  // Simulate pre-version (v0) data with invalid values → migration sanitizes
  settingsModule.resetPrefs();
  // Manually poison values and drop schemaVersion to 0
  const bad = {
    targetAudience: 'Unknown',
    analysisMode: 'slow',
    deepseekKeyStatus: 'maybe',
    modelCache: 'yes',
    autoUpdate: 'no',
  };
  for (const [k, v] of Object.entries(bad)) {
    // Access underlying store via module export is not provided; use setters to persist then downgrade version
    // setPrefs will sanitize, so we bypass by requiring module again with a fresh store
  }

  // Recreate module with a seeded store
  const SeededStore = class extends InMemoryStore {
    constructor(opts = {}) {
      super(opts);
      Object.assign(this.data, bad);
      this.data.schemaVersion = 0;
    }
  };
  const seededModule = proxyquire('../settingsStore', {
    electron,
    'electron-store': SeededStore,
  });
  seededModule.migrateIfNeeded();
  const migrated = seededModule.getPrefs();
  assert.strictEqual(migrated.targetAudience, 'Standard', 'invalid targetAudience should fallback');
  assert.strictEqual(migrated.analysisMode, 'better', 'invalid analysisMode should fallback');
  assert.strictEqual(migrated.deepseekKeyStatus, 'unset', 'invalid key status should fallback');
  assert.strictEqual(typeof migrated.modelCache, 'boolean');
  assert.strictEqual(typeof migrated.autoUpdate, 'boolean');
  assert.strictEqual(seededModule.getSchemaVersion(), seededModule.SETTINGS_SCHEMA_VERSION);

  console.log('OK: settings migrations');
})().catch((err) => { console.error('TEST FAILURE:', err); process.exit(1); });


