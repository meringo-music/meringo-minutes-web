// Runs before first paint so a chosen theme never flashes the other one.
try {
  var t = localStorage.getItem('theme');
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
} catch (e) { /* storage blocked: follow the system */ }
