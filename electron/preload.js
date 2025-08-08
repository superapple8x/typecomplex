// Preload script to run in isolated context.
// - Logs basic lifecycle events
// - Probes backend reachability from the renderer via fetch

(function () {
  const HEALTH_PATH = '/health';
  const CANDIDATE_HOSTS = ['127.0.0.1', 'localhost'];
  const CANDIDATE_PORTS = [5001];

  function log(...args) {
    try {
      // Prefix so main process can filter
      console.log('[preload]', ...args);
    } catch (_) {}
  }

  async function probeOnce() {
    for (const host of CANDIDATE_HOSTS) {
      for (const port of CANDIDATE_PORTS) {
        const url = `http://${host}:${port}${HEALTH_PATH}`;
        try {
          const resp = await fetch(url, { method: 'GET', cache: 'no-store', mode: 'no-cors' });
          log('fetch', url, 'ok:', resp.ok, 'status:', resp.status, 'type:', resp.type);
        } catch (e) {
          log('fetch', url, 'error:', String(e && e.message ? e.message : e));
        }
      }
    }
  }

  function startProbes() {
    // Run a few probes early to see connectivity
    let count = 0;
    const h = setInterval(() => {
      probeOnce().catch(() => {});
      count += 1;
      if (count >= 5) clearInterval(h);
    }, 1500);
  }

  try {
    window.addEventListener('DOMContentLoaded', () => {
      log('DOMContentLoaded');
      startProbes();
    });
  } catch (_) {
    // If window is not available, still attempt a one-shot probe after a short delay
    setTimeout(() => {
      log('no-window, running headless probe');
      probeOnce().catch(() => {});
    }, 500);
  }
})();
