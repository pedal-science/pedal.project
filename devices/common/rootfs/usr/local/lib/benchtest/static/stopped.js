// The Stop button's page: stop the service and say so. body[data-stopped] becomes true once the
// service has answered, failed when it could not be asked.
(() => {
  'use strict';
  const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  const status = document.getElementById('stop-state');
  history.replaceState(null, '', location.pathname);
  fetch('/api/shutdown', {method: 'POST', keepalive: true,
    headers: {'Authorization': 'Bearer ' + token, 'X-Benchtest-Client': 'browser'}})
    .then((response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      document.body.dataset.stopped = 'true';
      status.textContent = 'The service on the pedal has stopped.';
    })
    .catch(() => {
      document.body.dataset.stopped = 'failed';
      status.textContent = 'The service on the pedal did not answer: it may have stopped already.';
    });
})();
