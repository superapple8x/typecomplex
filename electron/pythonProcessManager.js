const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
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
    this.healthCheckIntervalMs = options.healthCheckIntervalMs || 5000;
    this.healthTimeoutMs = options.healthTimeoutMs || 20000;
    this.healthPollIntervalMs = options.healthPollIntervalMs || 300;

    this.extraEnv = options.extraEnv || {};

    this.child = null;
    this.healthInterval = null;
    this.restartAttempts = 0;
    this.consecutiveHealthFailures = 0;
    this.stopping = false;
  }

  start() {
    if (this.child) return; // already running

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
      this.emit('stdout', data.toString());
    });

    this.child.stderr.on('data', (data) => {
      this.emit('stderr', data.toString());
    });

    this.child.on('close', (code) => {
      this.emit('exit', code);
      this._teardownHeartbeat();
      this.child = null;

      if (this.stopping) {
        // do not restart on intentional stop
        return;
      }

      if (this.restartAttempts < this.maxRestartAttempts) {
        const delay = this._computeBackoffDelay();
        this.restartAttempts += 1;
        this.emit('restarting', { attempt: this.restartAttempts, delay });
        setTimeout(() => {
          this.start();
          this._awaitReadyThenEmit();
        }, delay);
      } else {
        this.emit('failed', { message: 'Max restart attempts exceeded' });
      }
    });

    this.child.on('error', (err) => {
      this.emit('error', err);
    });

    // First boot: wait for health then start heartbeat
    this._awaitReadyThenEmit();
  }

  async stop({ timeoutMs = 5000 } = {}) {
    this.stopping = true;
    this._teardownHeartbeat();
    const proc = this.child;
    if (!proc) return;

    try {
      proc.kill();
    } catch (_) {}

    await new Promise((resolve) => {
      const t = setTimeout(resolve, timeoutMs);
      proc.once('close', () => {
        clearTimeout(t);
        resolve();
      });
    });

    this.child = null;
    this.restartAttempts = 0;
    this.consecutiveHealthFailures = 0;
    this.stopping = false;
  }

  async _awaitReadyThenEmit() {
    try {
      await this.waitForHealth(this.healthUrl, this.healthTimeoutMs, this.healthPollIntervalMs);
      this.restartAttempts = 0;
      this.emit('ready', { url: `http://${this.host}:${this.port}` });
      this._startHeartbeat();
    } catch (e) {
      this.emit('unhealthy', { error: e });
    }
  }

  _startHeartbeat() {
    this._teardownHeartbeat();
    this.healthInterval = setInterval(async () => {
      try {
        await this.waitForHealth(this.healthUrl, 4000, 300);
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
}

module.exports = { PythonProcessManager };
