
const DEFAULT_TIMEOUT_MS = 10000;

function pickResponseParser(responseType, res) {
  if (responseType === 'arrayBuffer') return () => res.arrayBuffer();
  if (responseType === 'text') return () => res.text();
  // default json with content-type check
  const ctype = (res.headers && res.headers.get && res.headers.get('content-type')) || '';
  if (/application\/json/i.test(String(ctype))) {
    return () => res.json().catch(() => ({}));
  }
  return () => res.text();
}

function isAbortError(err) {
  return err && (err.name === 'AbortError' || String(err.message || err).toLowerCase().includes('aborted'));
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function sanitizePath(pathname) {
  if (!pathname) return '/';
  if (pathname.startsWith('http://') || pathname.startsWith('https://')) return pathname;
  return pathname.startsWith('/') ? pathname : ('/' + pathname);
}

function createApiClient({ resolveBaseUrl, logger = console } = {}) {
  if (typeof resolveBaseUrl !== 'function') {
    throw new Error('createApiClient requires a resolveBaseUrl function');
  }

  let memoizedBaseUrl = null;

  async function getBaseUrl() {
    if (memoizedBaseUrl) return memoizedBaseUrl;
    const base = await resolveBaseUrl();
    memoizedBaseUrl = String(base || '').replace(/\/$/, '');
    return memoizedBaseUrl;
  }

  async function request(pathname, {
    method = 'GET',
    headers = {},
    body = undefined,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    responseType = 'json',
  } = {}) {
    const start = Date.now();
    const base = await getBaseUrl();
    const url = (pathname.startsWith('http://') || pathname.startsWith('https://')) ? pathname : (base + sanitizePath(pathname));

    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), Math.max(1, timeoutMs));

    const doFetch = async () => {
      const res = await fetch(url, { method, headers, body, signal: controller.signal });
      const parse = pickResponseParser(responseType, res);
      const duration = Date.now() - start;
      try {
        if (!res.ok) {
          let data = null;
          try { data = await parse(); } catch (_) { /* noop */ }
          const message = (data && (data.error || data.message)) || res.statusText || 'http_error';
          logger && logger.debug && logger.debug('[api] http', { method, url, status: res.status, durationMs: duration });
          return { ok: false, type: 'http', status: res.status, message, data };
        }
        const data = await parse();
        logger && logger.debug && logger.debug('[api] ok', { method, url, status: res.status, durationMs: duration });
        return { ok: true, status: res.status, data };
      } catch (e) {
        // Parsing failure after ok/!ok path — treat as network-ish error
        logger && logger.warn && logger.warn('[api] parse_error', { method, url, durationMs: duration, err: e && e.message ? e.message : String(e) });
        return { ok: false, type: 'network', status: 0, message: 'parse_error' };
      } finally {
        clearTimeout(id);
      }
    };

    try {
      return await doFetch();
    } catch (err) {
      clearTimeout(id);
      const duration = Date.now() - start;
      if (isAbortError(err)) {
        logger && logger.warn && logger.warn('[api] timeout', { method, url, durationMs: duration });
        return { ok: false, type: 'timeout', status: 0, message: 'timeout' };
      }
      // transient network failure — single retry with small backoff
      logger && logger.warn && logger.warn('[api] network_error_first', { method, url, durationMs: duration, err: err && err.message ? err.message : String(err) });
      await sleep(Math.min(800, Math.max(200, Math.floor(DEFAULT_TIMEOUT_MS * 0.03))));
      // Retry once
      const controller2 = new AbortController();
      const id2 = setTimeout(() => controller2.abort(), Math.max(1, timeoutMs));
      try {
        const res = await fetch(url, { method, headers, body, signal: controller2.signal });
        const parse = pickResponseParser(responseType, res);
        const duration2 = Date.now() - start;
        if (!res.ok) {
          let data = null;
          try { data = await parse(); } catch (_) {}
          const message = (data && (data.error || data.message)) || res.statusText || 'http_error';
          logger && logger.debug && logger.debug('[api] http_after_retry', { method, url, status: res.status, durationMs: duration2 });
          return { ok: false, type: 'http', status: res.status, message, data };
        }
        const data = await parse();
        logger && logger.debug && logger.debug('[api] ok_after_retry', { method, url, status: res.status, durationMs: duration2 });
        return { ok: true, status: res.status, data };
      } catch (err2) {
        clearTimeout(id2);
        const duration2 = Date.now() - start;
        if (isAbortError(err2)) {
          logger && logger.warn && logger.warn('[api] timeout_after_retry', { method, url, durationMs: duration2 });
          return { ok: false, type: 'timeout', status: 0, message: 'timeout' };
        }
        logger && logger.warn && logger.warn('[api] network_error_after_retry', { method, url, durationMs: duration2, err: err2 && err2.message ? err2.message : String(err2) });
        return { ok: false, type: 'network', status: 0, message: (err2 && err2.message) || 'network_error' };
      }
    }
  }

  return { request, getBaseUrl, _setMemoizedBaseUrl: (v) => { memoizedBaseUrl = v; } };
}

module.exports = { createApiClient };
