// The footer hat's dialog, loaded by visit.js on the third press: the visit
// log in the app's window, with its own set-aside card. Written by this page;
// nothing in it is the app's output, and nothing leaves the tab.

import { formatVisit } from './visit-format.js';

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}

export function show(log) {
  document.querySelector('dialog.visit')?.remove();
  const { header, lines } = formatVisit([[0, 'arrive', location.pathname], ...log]);

  const body = el('div', { id: 'visit-aside', class: 'app-card-body', hidden: '' },
    el('p', {}, 'This visitor is going to buy it.'));
  const more = el('button', { type: 'button', class: 'app-link', 'aria-expanded': 'false', 'aria-controls': 'visit-aside' }, 'Show anyway');
  more.addEventListener('click', () => {
    const open = body.hidden;
    body.hidden = !open;
    more.setAttribute('aria-expanded', String(open));
    more.textContent = open ? 'Hide' : 'Show anyway';
  });
  const close = el('button', { type: 'button', class: 'app-button' }, 'Close');

  const dialog = el('dialog', { class: 'app-window visit', 'aria-labelledby': 'visit-title' },
    el('div', { class: 'app-bar', 'aria-hidden': 'true' },
      el('span', { class: 'app-lights' }, el('i'), el('i'), el('i')), el('span', { class: 'app-title' }, 'meringominutes.app')),
    el('div', { class: 'visit-body' },
      el('h2', { id: 'visit-title', class: 'app-meeting', tabindex: '-1', autofocus: '' }, 'Your visit to meringominutes.app'),
      el('p', { class: 'app-strip' }, el('span', { class: 'app-traced' }, header)),
      el('ol', { class: 'visit-lines' }, ...lines.map(({ t, text }) =>
        el('li', {}, el('span', { class: 'visit-t' }, t), el('span', {}, text)))),
      el('div', { class: 'app-card' },
        el('div', { class: 'app-card-head' }, el('h3', {}, '1 unverified sentence'), more),
        el('p', { class: 'app-card-line' }, 'Nothing you did on this page says that. Read it as a lead, not a finding.'),
        body),
      el('p', { class: 'visit-foot' }, 'Written by this page, not by Meringo Minutes. The list lived in this tab’s memory and goes when you close it. Nothing here was sent anywhere.'),
      el('p', { class: 'visit-close' }, close)));

  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
}
