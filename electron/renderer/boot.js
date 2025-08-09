(function(){
  // Resolve backend base URL via preload health check and transparently prefix relative fetch calls
  let backendBaseUrl = null;
  let ready = false;

  function dispatchReady() {
    try { window.dispatchEvent(new CustomEvent('backend:ready', { detail: { baseUrl: backendBaseUrl } })); } catch (_) {}
  }

  async function resolveBaseUrlWithRetry(retries = 20, delayMs = 500) {
    for (let i = 0; i < retries; i++) {
      try {
        if (!window.api || typeof window.api.healthCheck !== 'function') {
          await new Promise(r => setTimeout(r, 150));
          continue;
        }
        const res = await window.api.healthCheck();
        if (res && res.ok && res.baseUrl) {
          backendBaseUrl = String(res.baseUrl).replace(/\/$/, '');
          ready = true;
          dispatchReady();
          return backendBaseUrl;
        }
      } catch (_) {}
      await new Promise(r => setTimeout(r, delayMs));
    }
    return null;
  }

  // Patch fetch to prefix relative URLs with the backend base URL once known
  const originalFetch = window.fetch ? window.fetch.bind(window) : null;
  if (originalFetch) {
    window.fetch = async function(input, init) {
      try {
        let url = input;
        if (typeof url === 'string' && url.startsWith('/')) {
          if (!backendBaseUrl) {
            // Attempt to resolve on first need
            await resolveBaseUrlWithRetry(5, 300);
          }
          if (backendBaseUrl) url = backendBaseUrl + url;
        } else if (typeof Request !== 'undefined' && input instanceof Request) {
          const reqUrl = input.url || '';
          if (/^\//.test(reqUrl)) {
            if (!backendBaseUrl) {
              await resolveBaseUrlWithRetry(5, 300);
            }
            if (backendBaseUrl) {
              const nextUrl = backendBaseUrl + reqUrl;
              const rebuilt = new Request(nextUrl, input);
              return originalFetch(rebuilt, init);
            }
          }
        }
        return originalFetch(url, init);
      } catch (e) {
        return originalFetch(input, init);
      }
    };
  }

  // Expose a tiny helper API
  window.backend = {
    getBaseUrl: () => backendBaseUrl,
    isReady: () => ready,
    waitUntilReady: async () => {
      if (ready && backendBaseUrl) return backendBaseUrl;
      return resolveBaseUrlWithRetry(20, 300);
    },
  };

  // Kick off base URL resolution in the background
  resolveBaseUrlWithRetry(20, 300).catch(() => {});
})();


