// The footer hat's visit log as words, with no DOM: visit-dialog.js shows it
// and tests/visit.test.js checks it. An event is [ms since the page loaded,
// kind, value], recorded by visit.js. Values are fixed page text (a heading,
// a chip, a timestamp), a theme or a switch position: never anything typed.

// m:ss since the page loaded.
export function clock(ms) {
  const s = Math.max(0, Math.floor(Number(ms) / 1000) || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const flat = (text) => String(text ?? '').replace(/\s+/g, ' ').trim();

// A page's path as a visitor would say it.
export function pageName(path) {
  const p = flat(path) || '/';
  return p === '/' || p === '/index.html' ? 'the home page' : p;
}

// One event as a sentence, or null for anything unknown or empty.
function sentence([, kind, value]) {
  const v = flat(value);
  switch (kind) {
    case 'arrive': return `You arrived at ${pageName(value)}.`;
    case 'section': return v && `You reached “${v}”.`;
    case 'ts': return v && `You played the recording from ${v}.`;
    case 'chip': return v && `You asked the demo: “${v}”`;
    case 'audit': return value ? 'You turned on the audit.' : 'You turned the audit off again.';
    case 'script': return 'You opened “What was actually said”.';
    case 'theme-toggle': return v === 'light' || v === 'dark' ? `You switched to the ${v} theme.` : null;
    case 'hat': return 'You pressed the hat three times.';
    default: return null;
  }
}

// { header, lines: [{ t, text }] } in time order. FAQ questions become one
// line with their count, at the time of the last one: the words were never kept.
export function formatVisit(events) {
  const list = (Array.isArray(events) ? events : []).filter(Array.isArray);
  const faq = list.filter(([, kind]) => kind === 'faq');
  const lines = list
    .map((e) => ({ ms: Number(e[0]) || 0, text: sentence(e) }))
    .filter((l) => l.text);
  if (faq.length) {
    const n = faq.length;
    lines.push({
      ms: Math.max(...faq.map(([ms]) => Number(ms) || 0)),
      text: `You asked the FAQ box ${n} question${n === 1 ? '' : 's'}. I kept the count, not the words.`,
    });
  }
  lines.sort((a, b) => a.ms - b.ms);
  return {
    header: `All ${lines.length} lines traced to this visit`,
    lines: lines.map(({ ms, text }) => ({ t: clock(ms), text })),
  };
}
