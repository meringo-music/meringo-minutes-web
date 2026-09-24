// The home page demo: the app's own output for one made-up meeting, from
// assets/data/demo.json. In the window every word is the app's; my audit notes
// (.audit, .site-note) are a layer styled apart. Without JavaScript the
// plain-text version stands alone.

import { bankEngine } from './ask-bank.js';
import { askDemo, el } from './ask-ui.js';
import { secondsOf, tally, verdictText } from './demo-core.js';

const reduce = matchMedia('(prefers-reduced-motion: reduce)');

function build(section, demo) {
  const { app, site } = demo;
  const c = app.chrome;
  const cap = site.captions;
  const audit = site.audit;
  const audio = section.querySelector('audio');

  const counts = tally(demo);
  for (const n of section.querySelectorAll('[data-tally]')) n.textContent = counts[n.dataset.tally];

  const stamp = (ts, h) => el('button', {
    type: 'button', class: 'ts', 'data-t': secondsOf(ts), 'data-h': h, 'aria-label': cap.playFrom.replace('{ts}', ts),
  }, ts);

  // My note on one app string: its verdict in words, then the note if any.
  // A note with text shows once its item is opened; the rest wait for the toggle.
  const note = (h, { open = false, quote = null, tag = 'div' } = {}) => {
    const a = audit[h];
    if (!a) return null;
    return el(tag, { class: `audit${open && a.note ? ' is-open' : ''}`, 'data-for': h },
      el('p', { class: 'audit-v' }, quote ? `“${quote.split(' ').slice(0, 5).join(' ')}…” ` : '', verdictText(a, cap)),
      a.note && el('p', {}, a.note));
  };

  // Summary
  const summary = el('div', { class: 'app-doc' },
    el('div', { class: 'app-strip' },
      el('span', { class: 'app-traced' }, c.traced), el('span', { class: 'app-checked' }, c.checked)),
    el('h3', {}, app.summary.heading),
    el('p', {}, app.summary.overview), note(app.summary.overviewH));
  for (const sec of app.summary.sections) {
    summary.append(el('h4', {}, sec.heading));
    if (!sec.items.length) continue; // "Open Questions & Next Steps" is empty, as in the app
    summary.append(el('ul', { class: 'app-points' }, ...sec.items.map((it) => {
      const [first, ...rest] = it.sentences;
      const text = el('p', {}, el('strong', {}, it.label), `: ${first.text}`);
      for (const s of rest) text.append(` ${s.text}`, ...(s.show ? [' ', stamp(s.t, s.h)] : []));
      const many = it.sentences.length > 1;
      return el('li', {}, el('span', { class: 'gutter' }, stamp(first.t, first.h)), text,
        ...it.sentences.map((s) => note(s.h, { quote: many && s.text })));
    })));
  }
  const setAside = el('div', { id: 'setaside', class: 'app-card-body', hidden: true });
  let list = null;
  for (const it of app.setAside) {
    if (!it.label) { setAside.append(el('p', {}, it.text), note(it.h, { open: true })); continue; }
    if (!list) setAside.append(list = el('ul', { class: 'app-points' }));
    list.append(el('li', {}, el('p', {}, el('strong', {}, it.label), `: ${it.text}`), note(it.h, { open: true })));
  }
  const show = el('button', { type: 'button', class: 'app-link', 'aria-expanded': 'false', 'aria-controls': 'setaside' }, c.setAsideShow);
  show.addEventListener('click', () => {
    const open = setAside.hidden;
    setAside.hidden = !open;
    show.setAttribute('aria-expanded', String(open));
    show.textContent = open ? c.setAsideHide : c.setAsideShow;
  });
  summary.append(el('div', { class: 'app-card' },
    el('div', { class: 'app-card-head' }, el('h4', {}, c.setAsideHeading), show),
    el('p', { class: 'app-card-line' }, c.setAsideLine), setAside));

  // Transcript
  const lines = new Map();
  const transcript = el('ol', { class: 'app-lines' }, ...app.transcript.map((l) => {
    const li = el('li', { tabindex: '-1' }, stamp(l.t), el('span', { class: 'who' }, l.speaker), el('span', {}, l.text));
    lines.set(l.s, li);
    return li;
  }));

  // Ask, through ask-ui.js in demo mode
  const ask = askDemo({
    engine: bankEngine({ questions: app.asks }),
    questions: app.asks.map((q) => q.q),
    chrome: c,
    typed: cap.typed,
    stamp: (t) => stamp(t),
    decorate: (item) => note(item.h, { open: true }),
  });

  // Tabs, as the app has them (its Mindmap tab is left out)
  const views = {
    transcript: [c.tabTranscript, transcript],
    summary: [c.tabSummary, summary],
    ask: [c.tabAsk, el('div', {}, ask.form, ask.result, ask.status)],
  };
  const tabs = {};
  const panes = {};
  const tablist = el('div', { class: 'app-tabs', role: 'tablist', 'aria-label': app.title });
  for (const [k, [label, body]] of Object.entries(views)) {
    tabs[k] = el('button', { type: 'button', role: 'tab', id: `tab-${k}`, 'aria-controls': `pane-${k}` }, label);
    tabs[k].addEventListener('click', () => select(k));
    tablist.append(tabs[k]);
    panes[k] = el('div', { class: 'demo-pane', role: 'tabpanel', id: `pane-${k}`, 'aria-labelledby': `tab-${k}`, tabindex: '0' }, body);
  }
  function select(k) {
    for (const key of Object.keys(views)) {
      const on = key === k;
      tabs[key].setAttribute('aria-selected', String(on));
      tabs[key].tabIndex = on ? 0 : -1;
      panes[key].hidden = !on;
    }
  }
  tablist.addEventListener('keydown', (e) => {
    const keys = Object.keys(views);
    const i = keys.indexOf(e.target.id.slice(4));
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: keys.length - 1 }[e.key];
    if (j == null) return;
    e.preventDefault();
    const k = keys[(j + keys.length) % keys.length];
    select(k);
    tabs[k].focus();
  });
  select('summary');

  // A timestamp: the transcript opens at that line, and the recording plays from it.
  let current = null;
  const pin = el('li', { class: 'audit audit-pin' });
  function play(s, h) {
    const li = lines.get(s);
    if (!li) return;
    select('transcript');
    current?.removeAttribute('aria-current');
    li.setAttribute('aria-current', 'true');
    current = li;
    const a = h && audit[h];
    if (a) {
      pin.replaceChildren(...note(h, { open: true }).childNodes);
      pin.classList.toggle('is-open', Boolean(a.note));
      li.after(pin);
      if (a.note) for (const n of summary.querySelectorAll(`[data-for="${h}"]`)) n.classList.add('is-open');
    } else pin.remove();
    const pane = panes.transcript;
    pane.scrollTo({ top: li.offsetTop - 8, behavior: reduce.matches ? 'auto' : 'smooth' });
    li.focus({ preventScroll: true });
    audio.currentTime = s;
    audio.play().catch(() => {}); // a blocked play still leaves the playhead there
  }

  const win = el('div', { class: 'app-window demo-window', role: 'group', 'aria-label': `${c.window}: ${app.title}` },
    el('div', { class: 'app-bar', 'aria-hidden': 'true' },
      el('span', { class: 'app-lights' }, el('i'), el('i'), el('i')), el('span', { class: 'app-title' }, c.window)),
    el('div', { class: 'app-head' },
      el('p', { class: 'app-meeting' }, app.title),
      el('p', { class: 'app-meta' }, el('span', {}, c.date), el('span', {}, c.duration), el('span', { class: 'app-status' }, c.status))),
    tablist, ...Object.values(panes));
  win.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-t]');
    if (b) play(Number(b.dataset.t), b.dataset.h);
  });

  const tray = section.querySelector('[data-demo-tray]');
  tray.append(ask.chips);
  tray.addEventListener('click', (e) => {
    if (!e.target.closest('.chip')) return;
    select('ask');
    win.scrollIntoView({ block: 'nearest', behavior: reduce.matches ? 'auto' : 'smooth' });
  });

  const toggle = section.querySelector('[data-audit-toggle]');
  toggle.checked = false;
  toggle.addEventListener('change', () => { section.dataset.audit = toggle.checked ? 'on' : 'off'; });

  section.querySelector('[data-demo-mount]').replaceChildren(win);
  for (const n of section.querySelectorAll('[data-demo-js]')) n.hidden = false;
  section.querySelector('[data-demo-static]').hidden = true;
}

async function start(section) {
  let demo;
  try {
    const res = await fetch('/assets/data/demo.json');
    if (!res.ok) return;
    demo = await res.json();
  } catch {
    return; // no window; the static text version is still there
  }
  build(section, demo);
}

const section = document.getElementById('demo');
if (section) start(section);
