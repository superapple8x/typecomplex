const assert = require('assert');
const path = require('path');
const proxyquire = require('proxyquire');

function makeElectronStub() {
  const handlers = new Map();
  const ipcMain = {
    handle: (channel, fn) => { handlers.set(channel, fn); },
  };
  const createdWindows = [];
  class BrowserWindow {
    constructor(opts) {
      this.opts = opts;
      this._destroyed = false;
      this._events = {};
      createdWindows.push(this);
    }
    loadFile() { return Promise.resolve(); }
    isDestroyed() { return this._destroyed; }
    focus() { /* no-op */ }
    on(ev, cb) { this._events[ev] = cb; }
    show() { /* no-op */ }
  }
  const app = {
    name: 'TypeComplex',
    disableHardwareAcceleration: () => {},
    commandLine: { appendSwitch: () => {} },
    on: () => {}, // do not trigger ready handlers
    getPath: () => path.join(process.cwd(), '.userData'),
  };
  const Menu = { buildFromTemplate: () => ({ }), setApplicationMenu: () => {} };
  const dialog = { showOpenDialog: async () => ({ canceled: true }), showSaveDialog: async () => ({ canceled: true }) };
  const Notification = { isSupported: () => false };
  return { electron: { app, BrowserWindow, Notification, dialog, ipcMain, Menu }, handlers, createdWindows };
}

(async () => {
  const { electron, handlers, createdWindows } = makeElectronStub();
  // Load main.js with stubbed electron
  proxyquire('../main', { electron });

  // 1) settings:getPrefs should return defaults on first call
  const getPrefs = handlers.get('settings:getPrefs');
  assert.ok(typeof getPrefs === 'function', 'settings:getPrefs handler missing');
  const prefs1 = await getPrefs();
  assert.strictEqual(prefs1.targetAudience, 'Standard');
  assert.strictEqual(prefs1.analysisMode, 'better');
  assert.strictEqual(typeof prefs1.modelCache, 'boolean');
  assert.strictEqual(typeof prefs1.autoUpdate, 'boolean');

  // 2) settings:setPrefs should update and return merged prefs
  const setPrefs = handlers.get('settings:setPrefs');
  assert.ok(typeof setPrefs === 'function', 'settings:setPrefs handler missing');
  const next = await setPrefs({}, { partial: { targetAudience: 'General Public', analysisMode: 'fast', modelCache: false, autoUpdate: false } });
  assert.strictEqual(next.targetAudience, 'General Public');
  assert.strictEqual(next.analysisMode, 'fast');
  assert.strictEqual(next.modelCache, false);
  assert.strictEqual(next.autoUpdate, false);

  // 3) settings:openWindow should create a BrowserWindow and resolve ok
  const openWindow = handlers.get('settings:openWindow');
  assert.ok(typeof openWindow === 'function', 'settings:openWindow handler missing');
  const res = await openWindow();
  assert.deepStrictEqual(res, { ok: true });
  assert.ok(createdWindows.length >= 1, 'settings window not created');
  const win = createdWindows[0];
  assert.ok(win && win.opts && win.opts.title === 'Settings', 'settings window has wrong title/options');

  console.log('OK: settings IPC basic flows');
})().catch((err) => { console.error('TEST FAILURE:', err); process.exit(1); });
