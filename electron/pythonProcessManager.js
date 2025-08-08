const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { EventEmitter } = require('events');

class PythonProcessManager extends EventEmitter {
  constructor(options = {}) {
    super();
    this.pythonBinary = options.pythonBinary || process.env.PYTHON_BINARY || 'python3';
    this.serverPath = options.serverPath || path.join(__dirname, '..', 'electron_server.py');
    this.host = options.host || process.env.TYPECOMPLEX_HOST || '127.0.0.1';
    this.port = Number(options.port || process.env.TYPECOMPLEX_PORT || 5001);

    this.healthPath = options.healthPath || '/health';
    this.healthUrl = `http://${this.host}:${this.port}${this.healthPath}`;

    this.baseRestartDelayMs = options.baseRestartDelayMs || 1000;
    this.maxRestartAttempts = options.maxRestartAttempts || 3;
    this.maxBackoffCapMs = options.maxBackoffCapMs || 30000; // cap exponential backoff
    this.cooldownMs = options.cooldownMs || 120000; // after exhausting attempts
    this.autoRetryAfterCooldown = options.autoRetryAfterCooldown !== undefined ? options.autoRetryAfterCooldown : true;
    this.healthCheckIntervalMs = options.healthCheckIntervalMs || 5000;
    // Some environments do heavy first-time initialization (NLTK, spaCy, etc.).
    // Allow a generous initial readiness timeout, but keep polling if exceeded.
    this.healthTimeoutMs = options.healthTimeoutMs || 120000;
    this.healthPollIntervalMs = options.healthPollIntervalMs || 300;

    this.extraEnv = options.extraEnv || {};
    this.logDir = options.logDir || null; // directory to dump recent logs on failure

    this.child = null;
    this.healthInterval = null;
    this.restartAttempts = 0;
    this.consecutiveHealthFailures = 0;
    this.stopping = false;
    this.cooldownTimer = null;
    this.cooldownUntil = 0;
    this._killReason = null; // 'heartbeat' | 'manual' | null
    this.resetAttemptsOnNextHeartbeat = false;

    // Track rapid restarts to detect flapping
    this.recentRestartTimestamps = [];
    this.flapWindowMs = options.flapWindowMs || 120000; // 2 minutes
    this.flapThreshold = options.flapThreshold || 5; // restarts within window

    // In-memory ring buffer of recent stdout/stderr
    this.logBufferLimit = options.logBufferLimit || 500; // entries
    this.logBuffer = [];
  }

  start() {
    if (this.child) return; // already running
    if (this.cooldownTimer) {
      clearTimeout(this.cooldownTimer);
      this.cooldownTimer = null;
      this.cooldownUntil = 0;
    }

    const args = [this.serverPath, '--host', this.host, '--port', String(this.port)];
    const env = {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
      ELECTRON_APP_PATH: path.join(__dirname, '..'),
      // Avoid GPU / heavy frameworks initializing GPU in backend context
      CUDA_VISIBLE_DEVICES: '',
      MPLBACKEND: process.env.MPLBACKEND || 'Agg',
      OMP_NUM_THREADS: process.env.OMP_NUM_THREADS || '1',
      ...this.extraEnv,
    };

    this.child = spawn(this.pythonBinary, args, { env });

    this.child.stdout.on('data', (data) => {
      const text = data.toString();
      this._pushLog({ source: 'stdout', text });
      this.emit('stdout', text);
    });

    this.child.stderr.on('data', (data) => {
      const text = data.toString();
      this._pushLog({ source: 'stderr', text });
      this.emit('stderr', text);
    });

    this.child.on('close', (code, signal) => {
      const cause = this._killReason === 'heartbeat' ? 'heartbeat' : (this.stopping ? 'manual' : 'exit');
      this.emit('exit', { code, signal, cause });
      this._teardownHeartbeat();
      this.child = null;
      this._killReason = null;

      if (this.stopping) {
        // do not restart on intentional stop
        return;
      }

      // Detect flapping: too many restarts in a short window
      const now = Date.now();
      this._recordRestartTimestamp(now);

      if (this.restartAttempts < this.maxRestartAttempts) {
        const rawDelay = this._computeBackoffDelay();
        const delay = Math.min(this.maxBackoffCapMs, rawDelay);
        this.restartAttempts += 1;
        if (this._isFlapping(now)) {
          this._enterCooldown('flapping');
          return;
        }
        this.emit('restarting', { attempt: this.restartAttempts, delay, cause });
        setTimeout(() => {
          this.start();
          this._awaitReadyThenEmit();
        }, delay);
      } else {
        this._enterCooldown('max_attempts');
      }
    });

    this.child.on('error', (err) => {
      this.emit('error', err);
    });

    // First boot: wait for health then start heartbeat
    this._awaitReadyThenEmit();
  }

  async stop({ timeoutMs = 5000 } = {}) {
    if (this.stopping) {
      // Avoid duplicate stop sequences
      return;
    }
    this.stopping = true;
    this._teardownHeartbeat();
    const proc = this.child;
    if (!proc) {
      this.stopping = false;
      return;
    }

    // Try HTTP shutdown endpoint first (graceful)
    const tryHttpShutdown = () => new Promise((resolve) => {
      const url = `http://${this.host}:${this.port}/internal/shutdown`;
      try {
        const req = http.request(url, {
          method: 'POST',
          timeout: Math.min(2000, Math.max(500, timeoutMs - 1000)),
          headers: { 'X-TypeComplex-Internal': '1' },
        }, (res) => {
          res.resume();
          resolve(true);
        });
        req.on('timeout', () => { try { req.destroy(); } catch (_) {}; resolve(false); });
        req.on('error', () => resolve(false));
        req.end();
      } catch (_) {
        resolve(false);
      }
    });

    // Wait for process close with escalating signals
    await (async () => {
      const start = Date.now();
      const remaining = () => Math.max(0, timeoutMs - (Date.now() - start));
      const waitForClose = () => new Promise((resolve) => {
        const t = setTimeout(resolve, remaining());
        proc.once('close', () => { clearTimeout(t); resolve(); });
      });

      // Step 1: HTTP shutdown
      await tryHttpShutdown();
      await waitForClose();
      if (!this.child) return;

      // Step 2: SIGTERM
      try { proc.kill(); } catch (_) {}
      await waitForClose();
      if (!this.child) return;

      // Step 3: SIGKILL
      try { process.kill(proc.pid, 'SIGKILL'); } catch (_) {}
      await waitForClose();
    })();

    this.child = null;
    this.restartAttempts = 0;
    this.consecutiveHealthFailures = 0;
    this.stopping = false;
  }

  async _awaitReadyThenEmit() {
    const attemptReady = async () => {
      if (this.stopping || !this.child) return;
      try {
        await this.waitForHealth(this.healthUrl, this.healthTimeoutMs, this.healthPollIntervalMs);
        this.emit('ready', { url: `http://${this.host}:${this.port}` });
        this._startHeartbeat();
        this.resetAttemptsOnNextHeartbeat = true;
      } catch (e) {
        this.emit('unhealthy', { error: e });
        // Keep polling until the process becomes healthy or is stopped
        setTimeout(attemptReady, Math.min(2000, this.healthTimeoutMs / 10));
      }
    };
    attemptReady();
  }

  _startHeartbeat() {
    this._teardownHeartbeat();
    this.healthInterval = setInterval(async () => {
      try {
        await this.waitForHealth(this.healthUrl, 4000, 300);
        if (this.resetAttemptsOnNextHeartbeat) {
          this.restartAttempts = 0;
          this.resetAttemptsOnNextHeartbeat = false;
        }
        if (this.consecutiveHealthFailures > 0) {
          this.emit('healthy');
        }
        this.consecutiveHealthFailures = 0;
      } catch (e) {
        this.consecutiveHealthFailures += 1;
        this.emit('heartbeat-failed', { count: this.consecutiveHealthFailures });
        if (this.consecutiveHealthFailures >= 3) {
          // Controlled restart
          this.consecutiveHealthFailures = 0;
          if (this.child) {
            this.emit('heartbeat-restart');
            try {
              this._killReason = 'heartbeat';
              this.child.kill();
            } catch (_) {}
          }
        }
      }
    }, this.healthCheckIntervalMs);
  }

  _teardownHeartbeat() {
    if (this.healthInterval) {
      clearInterval(this.healthInterval);
      this.healthInterval = null;
    }
  }

  _computeBackoffDelay() {
    const base = this.baseRestartDelayMs * Math.pow(2, this.restartAttempts);
    const jitter = Math.floor(Math.random() * 250);
    return base + jitter;
  }

  waitForHealth(url, timeoutMs = 20000, intervalMs = 300) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      function schedule() {
        if (Date.now() - start > timeoutMs) {
          reject(new Error('Health check timed out'));
          return;
        }
        setTimeout(check, intervalMs);
      }
      function check() {
        try {
          const req = http.get(url, (res) => {
            // Drain response to free sockets
            res.resume();
            if (res.statusCode === 200) {
              resolve();
            } else {
              schedule();
            }
          });
          req.on('error', schedule);
        } catch (_) {
          schedule();
        }
      }
      check();
    });
  }

  getRecentLogs(maxEntries = 200) {
    const start = Math.max(0, this.logBuffer.length - maxEntries);
    return this.logBuffer.slice(start).map((e) => ({ ...e }));
  }

  _pushLog({ source, text }) {
    this.logBuffer.push({ ts: Date.now(), source, text });
    if (this.logBuffer.length > this.logBufferLimit) {
      this.logBuffer.splice(0, this.logBuffer.length - this.logBufferLimit);
    }
  }

  _recordRestartTimestamp(ts) {
    this.recentRestartTimestamps.push(ts);
    const cutoff = ts - this.flapWindowMs;
    this.recentRestartTimestamps = this.recentRestartTimestamps.filter((t) => t >= cutoff);
  }

  _isFlapping(nowTs) {
    const cutoff = nowTs - this.flapWindowMs;
    const count = this.recentRestartTimestamps.filter((t) => t >= cutoff).length;
    return count >= this.flapThreshold;
  }

  _enterCooldown(reason) {
    const now = Date.now();
    this.cooldownUntil = now + this.cooldownMs;
    const details = { message: 'Entering cooldown', reason, cooldownMs: this.cooldownMs, cooldownUntil: this.cooldownUntil };
    // Attempt to dump recent logs for diagnostics
    let logFile = null;
    try {
      if (this.logDir) {
        if (!fs.existsSync(this.logDir)) {
          fs.mkdirSync(this.logDir, { recursive: true });
        }
        logFile = path.join(this.logDir, `backend-${new Date(now).toISOString().replace(/[:.]/g, '-')}.log`);
        const lines = this.getRecentLogs(500).map((e) => {
          const dt = new Date(e.ts).toISOString();
          return `[${dt}] ${e.source.toUpperCase()}: ${e.text}`.replace(/\n$/, '');
        }).join('');
        fs.writeFileSync(logFile, lines, 'utf8');
        details.logFile = logFile;
      }
    } catch (_) {}

    this.emit('failed', details);

    if (this.autoRetryAfterCooldown) {
      if (this.cooldownTimer) clearTimeout(this.cooldownTimer);
      this.cooldownTimer = setTimeout(() => {
        this.cooldownTimer = null;
        this.restartAttempts = 0;
        this.start();
        this._awaitReadyThenEmit();
      }, this.cooldownMs);
    }
  }
}

module.exports = { PythonProcessManager };
