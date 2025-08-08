const assert = require('assert');
const { createApiClient } = require('../apiClient');

function makeFetchStubSequence(steps) {
  let call = 0;
  global.fetch = async function(url, opts) {
    const s = steps[Math.min(call, steps.length - 1)];
    call += 1;
    if (s.type === 'throw') {
      throw new Error(s.error || 'net');
    }
    // emulate minimal Response
    return {
      ok: s.ok !== false,
      status: s.status || 200,
      headers: { get: (k) => s.headers && s.headers[k.toLowerCase()] },
      json: async () => s.json !== undefined ? s.json : {},
      text: async () => s.text !== undefined ? s.text : '',
      arrayBuffer: async () => s.arrayBuffer !== undefined ? s.arrayBuffer : new ArrayBuffer(0),
    };
  };
}

(async () => {
  const api = createApiClient({ resolveBaseUrl: async () => 'http://127.0.0.1:5001', logger: { debug(){}, warn(){} } });

  // 1) Success JSON
  makeFetchStubSequence([{ ok: true, status: 200, headers: { 'content-type': 'application/json' }, json: { hello: 'world' } }]);
  let r = await api.request('/health');
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.data, { hello: 'world' });

  // 2) HTTP 429, no retry, normalized error
  makeFetchStubSequence([{ ok: false, status: 429, headers: { 'content-type': 'application/json' }, json: { error: 'rate_limited' } }]);
  r = await api.request('/ai/rewrite', { method: 'POST' });
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.type, 'http');
  assert.strictEqual(r.status, 429);
  assert.strictEqual(r.message, 'rate_limited');

  // 3) Network error then success with retry
  makeFetchStubSequence([
    { type: 'throw', error: 'ECONNRESET' },
    { ok: true, status: 200, headers: { 'content-type': 'application/json' }, json: { ok: 1 } },
  ]);
  r = await api.request('/health');
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.data, { ok: 1 });

  // 4) Timeout
  global.fetch = async function(url, opts) {
    return new Promise((_resolve, _reject) => {});
  };
  r = await api.request('/slow', { timeoutMs: 50 });
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.type, 'timeout');

  console.log('OK: apiClient basic behaviors');
})().catch((err) => { console.error('TEST FAILURE:', err); process.exit(1); });
