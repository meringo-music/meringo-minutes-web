// The FAQ assistant on /faq/. It answers from assets/data/faq.json, in the
// browser, with ask-core.js; what you type is never stored or sent anywhere.
// It is added by this script, so with JavaScript off it doesn't appear and the
// static FAQ below it stands alone.

import MiniSearch from '/assets/vendor/minisearch-7.1.2.js';
import { answerParts, answerText, faqEngine } from './ask-core.js';

const EMAIL = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/gi;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === true) node.setAttribute(k, '');
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  node.append(...children);
  return node;
}

// Plain text with its email addresses as mailto links.
function withEmail(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(EMAIL)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(el('a', { href: `mailto:${m[0]}` }, m[0]));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// An answer as nodes: text, root-relative links and email links only.
function answerNodes(answer) {
  return answerParts(answer).flatMap((p) => (p.href ? [el('a', { href: p.href }, p.text)] : withEmail(p.text)));
}

function openEntry(id) {
  const target = id && document.getElementById(id);
  if (target instanceof HTMLDetailsElement) target.open = true;
}

function build(data, engine) {
  const input = el('input', {
    id: 'ask-q', name: 'q', type: 'text', autocomplete: 'off', autocapitalize: 'sentences',
    spellcheck: 'true', enterkeyhint: 'search', maxlength: '300', 'aria-describedby': 'ask-disclosure',
  });
  const result = el('div', { class: 'ask-result', hidden: true });
  const status = el('p', { class: 'visually-hidden', role: 'status', 'aria-live': 'polite' });
  const contact = data.contact || 'support@meringo.app';

  const form = el('form', { class: 'ask-body', role: 'search', 'aria-label': 'Ask the FAQ' },
    el('label', { for: 'ask-q', class: 'ask-label' }, 'Ask a question'),
    el('p', { id: 'ask-disclosure', class: 'ask-disclosure' }, data.disclosure),
    el('div', { class: 'ask-row' }, input, el('button', { type: 'submit', class: 'button button-quiet ask-submit' }, 'Ask')),
    result,
    status,
  );

  function show(nodes, spoken) {
    result.replaceChildren(...nodes);
    result.hidden = false;
    // Clear first, so asking the same thing twice is announced twice.
    status.textContent = '';
    requestAnimationFrame(() => { status.textContent = spoken; });
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const question = input.value.trim();
    input.focus();
    if (!question) return;
    const r = engine.ask(question);
    if (r.kind === 'answer') {
      const { entry } = r;
      const link = el('a', { href: `#${entry.id}` }, entry.q);
      link.addEventListener('click', () => openEntry(entry.id));
      show([
        el('p', { class: 'ask-matched' }, 'Closest question I have: ', link),
        el('p', { class: 'ask-answer' }, ...answerNodes(entry.answer)),
      ], `Closest question I have: ${entry.q} ${answerText(entry.answer)}`);
    } else {
      const write = `Write to me at ${contact}.`;
      show([
        el('p', { class: 'ask-answer' }, data.refusal),
        el('p', { class: 'ask-contact' }, ...withEmail(write)),
      ], `${data.refusal} ${write}`);
    }
  });

  return el('section', { class: 'ask', 'aria-label': 'FAQ assistant' },
    el('div', { class: 'ask-bar', 'aria-hidden': 'true' },
      el('span', { class: 'ask-lights' }, el('i'), el('i'), el('i')),
      el('span', { class: 'ask-title' }, 'meringominutes.app')),
    form,
  );
}

async function start(mount) {
  let data;
  try {
    const res = await fetch('/assets/data/faq.json');
    if (!res.ok) return;
    data = await res.json();
  } catch {
    return; // no box; the static FAQ is still there
  }
  mount.replaceChildren(build(data, faqEngine(data, MiniSearch)));
}

// A link to /faq/#f12 opens that question, from this page or another.
window.addEventListener('hashchange', () => openEntry(location.hash.slice(1)));
openEntry(location.hash.slice(1));

const mount = document.querySelector('[data-ask-faq]');
if (mount) start(mount);
