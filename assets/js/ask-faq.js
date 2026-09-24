// FAQ mode of Ask, on /faq/: answers from assets/data/faq.json through
// ask-core.js and MiniSearch, loaded here and nowhere else. ask-ui.js imports
// this file only when the page has the FAQ box; the shared layout is there.

import { el, presenter, withEmail } from './ask-ui.js';

function openEntry(id) {
  const target = id && document.getElementById(id);
  if (target instanceof HTMLDetailsElement) target.open = true;
}

function buildFaq(data, engine, core) {
  // An answer as nodes: text, root-relative links and email links only.
  const answerNodes = (answer) => core.answerParts(answer)
    .flatMap((p) => (p.href ? [el('a', { href: p.href }, p.text)] : withEmail(p.text)));
  const input = el('input', {
    id: 'ask-q', name: 'q', type: 'text', autocomplete: 'off', autocapitalize: 'sentences',
    spellcheck: 'true', enterkeyhint: 'search', maxlength: '300', 'aria-describedby': 'ask-disclosure',
  });
  const result = el('div', { class: 'ask-result', hidden: true });
  const status = el('p', { class: 'visually-hidden', role: 'status', 'aria-live': 'polite' });
  const contact = data.contact || 'support@meringo.app';
  const show = presenter(result, status);

  const form = el('form', { class: 'ask-body', role: 'search', 'aria-label': 'Ask the FAQ' },
    el('label', { for: 'ask-q', class: 'ask-label' }, 'Ask a question'),
    el('p', { id: 'ask-disclosure', class: 'ask-disclosure' }, data.disclosure),
    el('div', { class: 'ask-row' }, input, el('button', { type: 'submit', class: 'button button-quiet ask-submit' }, 'Ask')),
    result,
    status,
  );

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
      ], `Closest question I have: ${entry.q} ${core.answerText(entry.answer)}`);
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

async function startFaq(mount) {
  let data, core, MiniSearch;
  try {
    const res = await fetch('/assets/data/faq.json');
    if (!res.ok) return;
    [data, core, { default: MiniSearch }] = await Promise.all([
      res.json(), import('./ask-core.js'), import('/assets/vendor/minisearch-7.1.2.js'),
    ]);
  } catch {
    return; // no box; the static FAQ is still there
  }
  mount.replaceChildren(buildFaq(data, core.faqEngine(data, MiniSearch), core));
}

const mount = document.querySelector('[data-ask-faq]');
if (mount) {
  // A link to /faq/#f12 opens that question, from this page or another.
  window.addEventListener('hashchange', () => openEntry(location.hash.slice(1)));
  openEntry(location.hash.slice(1));
  startFaq(mount);
}
