// Ask in the app's layout. Demo mode (on /) answers only the 16 questions the
// app was asked; FAQ mode (ask-faq.js, /faq/ only) answers from the FAQ.
// What you type is never stored or sent anywhere.

const EMAIL = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/gi;

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === true) node.setAttribute(k, '');
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  node.append(...children.filter((c) => c != null && c !== false));
  return node;
}

// Plain text with its email addresses as mailto links.
export function withEmail(text) {
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

// Shows nodes in the result area and says them to a screen reader. The live
// region is cleared first, so asking the same thing twice is announced twice.
export function presenter(result, status) {
  return (nodes, spoken) => {
    result.replaceChildren(...nodes.filter(Boolean));
    result.hidden = false;
    status.textContent = '';
    requestAnimationFrame(() => { status.textContent = typeof spoken === 'function' ? spoken() : spoken; });
  };
}

// Demo mode.
// engine: bankEngine over the 16 exchanges. chrome: the app's on-screen words.
// typed: my message for any other question. stamp(t): a play button for a
// citation. decorate(item): my audit note for an exchange, or null.
export function askDemo({ engine, questions, chrome, typed, stamp, decorate }) {
  const input = el('input', {
    id: 'demo-q', type: 'text', autocomplete: 'off', maxlength: '300', placeholder: chrome.askPlaceholder,
  });
  const result = el('div', { class: 'ask-result', hidden: true });
  const status = el('p', { class: 'visually-hidden', role: 'status', 'aria-live': 'polite' });
  const show = presenter(result, status);

  function answer(question) {
    const r = engine.ask(question);
    if (r.kind !== 'banked') {
      show([el('p', { class: 'site-note' }, ...withEmail(typed))], typed);
      return;
    }
    const { item } = r;
    const body = el('div', { class: 'ask-exchange', 'data-lint': 'app' });
    for (const s of item.answer) {
      body.append(el('p', { class: 'ask-sentence' }, s.text));
      for (const c of s.cites) body.append(el('p', { class: 'ask-cite' }, stamp(c.t), ` ${c.speaker}: ${c.text}`));
    }
    if (item.footnote) body.append(el('p', { class: 'ask-foot' }, item.footnote));
    const note = decorate(item);
    // A note is read out only when it's on screen (flagged, or the audit is on).
    const said = () => [...item.answer.map((s) => s.text), item.footnote, note?.offsetParent && note.textContent];
    show([body, note], () => said().filter(Boolean).join(' '));
  }

  const form = el('form', { class: 'app-ask', role: 'search', 'aria-label': 'Ask this meeting' },
    el('label', { for: 'demo-q', class: 'visually-hidden' }, 'Question'),
    input,
    el('span', { class: 'app-scope' }, chrome.askScope),
    el('button', { type: 'submit', class: 'app-button' }, chrome.askButton));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const q = input.value.trim();
    if (q) answer(q);
  });

  const chips = el('ul', { class: 'chips' }, ...questions.map((q) => {
    const b = el('button', { type: 'button', class: 'chip' }, q);
    b.addEventListener('click', () => { input.value = q; answer(q); });
    return el('li', {}, b);
  }));

  return { form, result, status, chips };
}

// FAQ mode, only on the page that has its box.
if (document.querySelector('[data-ask-faq]')) import('./ask-faq.js');
