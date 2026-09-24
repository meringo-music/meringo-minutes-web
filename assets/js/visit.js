// The footer hat's toy, listed in this tab's memory: never stored or sent, never typed text.
const log = [];
const d = document;
const add = (kind, value) => log.push([performance.now(), kind, value]);
const on = (type, f, c) => d.addEventListener(type, ({ target: t, timeStamp }) => f(t, timeStamp), c);
let hat = [];

const io = new IntersectionObserver((es) => es.forEach(({ isIntersecting, target: h }) => {
  if (isIntersecting) { io.unobserve(h); add('section', h.textContent); }
}));
d.querySelectorAll('main h2').forEach((h) => io.observe(h));

on('click', (t, now) => {
  const b = t.closest('.chip,button.ts,[data-theme-toggle],.hat');
  if (b?.className != 'hat') return b && add(b.className, b.textContent.trim() || getComputedStyle(d.documentElement).colorScheme);
  hat = hat.filter((x) => now - x < 2e3).concat(now);
  if (hat[2]) { hat = []; add('hat'); import('./visit-dialog.js').then((m) => m.show(log)); }
});
on('change', (t) => t.matches('[data-audit-toggle]') && add('audit', t.checked));
on('submit', (t) => t.q?.value.trim() && add('faq'));
on('toggle', (t) => t.open && t.matches('.demo-script') && add('script'), true);
