(function(){
  const logEl = document.getElementById('log');
  const statusText = document.getElementById('status-text');
  const backendUrlEl = document.getElementById('backend-url');
  const detailsEl = document.getElementById('details');
  const btnCheck = document.getElementById('btn-check');
  const btnOpen = document.getElementById('btn-open');

  function log(msg) {
    const ts = new Date().toISOString();
    logEl.textContent += `[${ts}] ${msg}\n`;
    logEl.scrollTop = logEl.scrollHeight;
  }

  async function checkHealth() {
    try {
      statusText.textContent = 'Checking…';
      const result = await window.api.healthCheck();
      backendUrlEl.textContent = result.baseUrl || '(unknown)';
      if (result.ok) {
        statusText.textContent = 'Healthy';
        statusText.className = 'ok';
        detailsEl.textContent = JSON.stringify(result.data || {}, null, 2);
        log('Health OK');
      } else {
        statusText.textContent = 'Unreachable';
        statusText.className = 'warn';
        detailsEl.textContent = result.error || 'Unreachable';
        log('Health unreachable');
      }
    } catch (e) {
      statusText.textContent = 'Error';
      statusText.className = 'error';
      const msg = e && e.message ? e.message : String(e);
      detailsEl.textContent = msg;
      log('Health error: ' + msg);
    }
  }

  async function openFile() {
    try {
      const filePath = await window.api.selectPdf();
      if (filePath) {
        log('Selected: ' + filePath);
      } else {
        log('File selection canceled');
      }
    } catch (e) {
      log('Open file error: ' + (e && e.message ? e.message : e));
    }
  }

  btnCheck.addEventListener('click', checkHealth);
  btnOpen.addEventListener('click', openFile);

  // Auto-check on first load after a short delay
  setTimeout(checkHealth, 700);
})();
