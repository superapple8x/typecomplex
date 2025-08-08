(function(){
  const logEl = document.getElementById('log');
  const statusText = document.getElementById('status-text');
  const backendUrlEl = document.getElementById('backend-url');
  const detailsEl = document.getElementById('details');
  const btnCheck = document.getElementById('btn-check');
  const btnOpen = document.getElementById('btn-open');
  const dropzone = document.getElementById('dropzone');
  const jobEl = document.getElementById('job');
  const taskIdEl = document.getElementById('task-id');
  const taskStateEl = document.getElementById('task-state');
  const taskMsgEl = document.getElementById('task-msg');
  const btnCancel = document.getElementById('btn-cancel');
  let activeTaskId = null;

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
        await startProcess(filePath);
      } else {
        log('File selection canceled');
      }
    } catch (e) {
      log('Open file error: ' + (e && e.message ? e.message : e));
    }
  }

  async function startProcess(filePath) {
    if (activeTaskId) {
      log('A task is already running; please wait or cancel.');
      return;
    }
    statusText.textContent = 'Uploading…';
    statusText.className = 'warn';
    try {
      const res = await window.api.processPdf(filePath, {
        action: 'full_analysis',
        target_audience: 'Standard',
        analysis_mode: 'best',
        include_overview_page: true,
        overview_top_x_count: 5,
        overview_top_x_type: 'complex',
        overview_show_visual_map: true,
      });
      if (!res || !res.ok) {
        throw new Error(res && res.error ? res.error : 'Unknown error');
      }
      activeTaskId = res.taskId;
      jobEl.style.display = '';
      taskIdEl.textContent = activeTaskId;
      taskStateEl.textContent = 'PENDING';
      taskMsgEl.textContent = 'Waiting for processing…';
      log('Task started: ' + activeTaskId);
    } catch (e) {
      statusText.textContent = 'Error';
      statusText.className = 'error';
      const msg = e && e.message ? e.message : String(e);
      detailsEl.textContent = msg;
      log('Start process error: ' + msg);
    }
  }

  // Subscribe to progress updates
  window.api.onPdfProgress(({ taskId, state, meta, statusMessage }) => {
    if (!activeTaskId || taskId !== activeTaskId) return;
    taskStateEl.textContent = state;
    taskMsgEl.textContent = statusMessage || state;
    statusText.textContent = state === 'PROGRESS' ? 'Processing…' : state;
    statusText.className = state === 'PROGRESS' ? 'warn' : (state === 'SUCCESS' ? 'ok' : 'muted');
    if (meta && typeof meta.progress === 'number') {
      detailsEl.textContent = `Progress: ${meta.progress}%`;
    }
  });

  window.api.onPdfDone(({ taskId, savedPath, canceled }) => {
    if (!activeTaskId || taskId !== activeTaskId) return;
    statusText.textContent = 'Done';
    statusText.className = 'ok';
    if (canceled) {
      detailsEl.textContent = 'Save canceled by user';
      log('Save canceled');
    } else {
      detailsEl.textContent = savedPath ? ('Saved to: ' + savedPath) : 'Completed';
      log('Saved to: ' + (savedPath || '(not saved)'));
    }
    activeTaskId = null;
    jobEl.style.display = 'none';
  });

  window.api.onPdfError(({ taskId, error }) => {
    if (!activeTaskId || taskId !== activeTaskId) return;
    statusText.textContent = 'Error';
    statusText.className = 'error';
    detailsEl.textContent = error || 'Unknown error';
    log('Error: ' + (error || 'Unknown error'));
    activeTaskId = null;
    jobEl.style.display = 'none';
  });

  // Drag-and-drop support
  function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
  ['dragenter','dragover','dragleave','drop'].forEach(ev => {
    dropzone.addEventListener(ev, preventDefaults, false);
  });
  dropzone.addEventListener('dragover', () => { dropzone.style.background = '#f1f5f9'; });
  dropzone.addEventListener('dragleave', () => { dropzone.style.background = ''; });
  dropzone.addEventListener('drop', async (e) => {
    dropzone.style.background = '';
    const dt = e.dataTransfer;
    if (!dt || !dt.files || dt.files.length === 0) return;
    const file = dt.files[0];
    if (!file || !file.path || !/\.pdf$/i.test(file.path)) {
      log('Dropped file is not a PDF.');
      return;
    }
    await startProcess(file.path);
  });

  btnCancel.addEventListener('click', async () => {
    if (!activeTaskId) return;
    try {
      log('Cancelling task: ' + activeTaskId);
      await window.api.cancelPdf(activeTaskId);
    } catch (_) {}
  });

  btnCheck.addEventListener('click', checkHealth);
  btnOpen.addEventListener('click', openFile);

  // Auto-check on first load after a short delay
  setTimeout(checkHealth, 700);
})();
