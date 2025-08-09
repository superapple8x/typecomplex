(function(){
  function onReady(fn){ if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', fn); } else { fn(); } }

  onReady(() => {
    try {
      const settingsBtn = document.getElementById('open-settings-btn');
      if (settingsBtn && window.settings && typeof window.settings.openWindow === 'function') {
        settingsBtn.classList.remove('hidden');
        settingsBtn.addEventListener('click', async () => {
          try { await window.settings.openWindow(); } catch (_) {}
        });
      }
    } catch (_) {}
  });
})();


