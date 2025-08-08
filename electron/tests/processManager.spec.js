const assert = require('assert');
const path = require('path');
const fs = require('fs');
const { EventEmitter } = require('events');
const proxyquire = require('proxyquire');

function createSpawnStub({ closeAfterMs = 5 }) {
  let spawnCount = 0;
  const children = [];
  function spawnStub() {
    spawnCount += 1;
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    // Emit a little output
    setTimeout(() => child.stdout.emit('data', Buffer.from(`child${spawnCount}: hello\n`)), 0);
    setTimeout(() => child.stderr.emit('data', Buffer.from(`child${spawnCount}: warn\n`)), 1);
    // Auto-close to trigger restart logic
    setTimeout(() => child.emit('close', 1, null), closeAfterMs);
    children.push(child);
    return child;
  }
  return { spawnStub, get spawnCount() { return spawnCount; }, children };
}

async function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function run() {
  // Temp log dir
  const tmp = path.join(__dirname, '..', 'tmp-test-logs');
  fs.mkdirSync(tmp, { recursive: true });

  const { spawnStub } = createSpawnStub({ closeAfterMs: 5 });
  const { PythonProcessManager } = proxyquire('../pythonProcessManager', {
    'child_process': { spawn: spawnStub },
  });

  const mgr = new PythonProcessManager({
    baseRestartDelayMs: 5,
    maxBackoffCapMs: 10,
    cooldownMs: 80,
    maxRestartAttempts: 1,
    healthTimeoutMs: 10,
    healthCheckIntervalMs: 10,
    autoRetryAfterCooldown: false,
    logDir: tmp,
  });
  // Short-circuit health checks
  // First start is healthy quickly, subsequent starts are also healthy
  mgr.waitForHealth = () => Promise.resolve();

  const events = [];
  mgr.on('restarting', (e) => events.push(['restarting', e]));
  mgr.on('failed', (e) => events.push(['failed', e]));
  mgr.on('ready', (e) => events.push(['ready', e]));

  mgr.start();
  // Allow enough time for: start -> close -> restarting -> start -> close -> failed
  await delay(200);

  // Expectations
  const restartingEvents = events.filter(([t]) => t === 'restarting');
  const failedEvents = events.filter(([t]) => t === 'failed');

  // Since the child closes twice with maxRestartAttempts=1, we expect exactly 1 restart
  assert.strictEqual(restartingEvents.length, 1, `expected 1 restarting, got ${restartingEvents.length}`);
  assert.ok(failedEvents.length === 1, `expected 1 failed, got ${failedEvents.length}`);
  const failedPayload = failedEvents[0][1];
  assert.ok(['max_attempts', 'flapping'].includes(failedPayload.reason), 'expected reason in failed event');
  if (failedPayload.logFile) {
    assert.ok(fs.existsSync(failedPayload.logFile), 'log file should exist');
  }

  console.log('OK: basic restart/cooldown workflow');
}

run().catch((err) => {
  console.error('TEST FAILURE:', err);
  process.exit(1);
});
