(function(){
  function $(id){ return document.getElementById(id); }
  const tabPrefs = $('tab-prefs');
  const tabApi = $('tab-api');
  const panelPrefs = $('panel-prefs');
  const panelApi = $('panel-api');

  function activate(tab){
    if (tab === 'prefs'){
      tabPrefs.classList.add('active'); tabApi.classList.remove('active');
      panelPrefs.style.display = ''; panelApi.style.display = 'none';
    } else {
      tabApi.classList.add('active'); tabPrefs.classList.remove('active');
      panelApi.style.display = ''; panelPrefs.style.display = 'none';
    }
  }
  tabPrefs.addEventListener('click', () => activate('prefs'));
  tabApi.addEventListener('click', () => activate('api'));

  const targetAudience = $('targetAudience');
  const analysisMode = $('analysisMode');
  const modelCache = $('modelCache');
  const autoUpdate = $('autoUpdate');
  const savePrefs = $('savePrefs');
  const resetPrefs = $('resetPrefs');
  const prefsStatus = $('prefsStatus');

  const keyStatus = $('keyStatus');
  const apiKeyInput = $('apiKeyInput');
  const btnSetKey = $('btnSetKey');
  const btnTestKey = $('btnTestKey');
  const btnDeleteKey = $('btnDeleteKey');
  const keyTestResult = $('keyTestResult');

  async function loadPrefs(){
    try {
      const prefs = await window.settings.getPrefs();
      targetAudience.value = prefs.targetAudience || 'Standard';
      analysisMode.value = prefs.analysisMode || 'better';
      modelCache.checked = Boolean(prefs.modelCache);
      autoUpdate.checked = Boolean(prefs.autoUpdate);
    } catch (e) {
      prefsStatus.textContent = 'Failed to load preferences';
      prefsStatus.className = 'status error';
    }
  }

  async function savePrefsFn(){
    try {
      const next = await window.settings.setPrefs({
        targetAudience: targetAudience.value,
        analysisMode: analysisMode.value,
        modelCache: Boolean(modelCache.checked),
        autoUpdate: Boolean(autoUpdate.checked),
      });
      prefsStatus.textContent = 'Saved';
      prefsStatus.className = 'status ok';
      setTimeout(() => { prefsStatus.textContent = ''; prefsStatus.className = 'status muted'; }, 1500);
    } catch (e) {
      prefsStatus.textContent = 'Save failed';
      prefsStatus.className = 'status error';
    }
  }

  async function resetPrefsFn(){
    try {
      const next = await window.settings.setPrefs({
        targetAudience: 'Standard',
        analysisMode: 'better',
        modelCache: true,
        autoUpdate: true,
      });
      await loadPrefs();
      prefsStatus.textContent = 'Defaults restored';
      prefsStatus.className = 'status ok';
      setTimeout(() => { prefsStatus.textContent = ''; prefsStatus.className = 'status muted'; }, 1500);
    } catch (e) {
      prefsStatus.textContent = 'Reset failed';
      prefsStatus.className = 'status error';
    }
  }

  async function refreshKeyStatus(){
    try {
      const res = await window.settings.getKeyStatus();
      const s = res && res.status ? String(res.status) : 'unset';
      keyStatus.textContent = (s === 'set') ? 'set' : 'unset';
      keyStatus.className = (s === 'set') ? 'ok' : 'warn';
    } catch (e) {
      keyStatus.textContent = 'unknown';
      keyStatus.className = 'warn';
    }
  }

  async function setKey(){
    try {
      const key = String(apiKeyInput.value || '').trim();
      if (!key || key.length < 10) { keyTestResult.textContent = 'Please enter a valid key'; keyTestResult.className = 'status warn'; return; }
      const res = await window.settings.setApiKey(key);
      apiKeyInput.value = '';
      await refreshKeyStatus();
      keyTestResult.textContent = res && res.ok ? 'Key set' : (res && res.error ? ('Error: ' + res.error) : 'Set failed');
      keyTestResult.className = (res && res.ok) ? 'status ok' : 'status error';
    } catch (e) {
      keyTestResult.textContent = 'Set failed';
      keyTestResult.className = 'status error';
    }
  }

  async function testKey(){
    try {
      keyTestResult.textContent = 'Testing…';
      keyTestResult.className = 'status muted';
      const res = await window.settings.testApiKey();
      if (res && res.ok) {
        keyTestResult.textContent = 'Connectivity OK';
        keyTestResult.className = 'status ok';
      } else {
        keyTestResult.textContent = 'Connectivity failed' + (res && res.error ? (': ' + res.error) : '');
        keyTestResult.className = 'status error';
      }
    } catch (e) {
      keyTestResult.textContent = 'Test failed';
      keyTestResult.className = 'status error';
    }
  }

  async function deleteKey(){
    try {
      const res = await window.settings.deleteApiKey();
      await refreshKeyStatus();
      keyTestResult.textContent = (res && res.ok) ? 'Key removed' : 'Remove failed';
      keyTestResult.className = (res && res.ok) ? 'status ok' : 'status error';
    } catch (e) {
      keyTestResult.textContent = 'Remove failed';
      keyTestResult.className = 'status error';
    }
  }

  savePrefs.addEventListener('click', savePrefsFn);
  resetPrefs.addEventListener('click', resetPrefsFn);
  btnSetKey.addEventListener('click', setKey);
  btnTestKey.addEventListener('click', testKey);
  btnDeleteKey.addEventListener('click', deleteKey);

  // Init
  loadPrefs();
  refreshKeyStatus();
})();
