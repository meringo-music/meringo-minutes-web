import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { bankEngine, normalize } from '../assets/js/ask-bank.js';
import { secondsOf, tally, verdictText } from '../assets/js/demo-core.js';

const demo = JSON.parse(readFileSync(new URL('../assets/data/demo.json', import.meta.url), 'utf8'));
const home = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const asks = demo.app.asks;
const bank = bankEngine({ questions: asks });

// Every string of every answer the app gave, to prove none leaks out unbanked.
const appText = asks.flatMap((a) => [
  ...a.answer.flatMap((s) => [s.text, ...s.cites.map((c) => c.text)]), a.footnote,
]).filter(Boolean);

test('the bank holds the 16 questions the app was asked', () => {
  assert.equal(asks.length, 16);
  assert.deepEqual(asks.map((a) => a.n), [...Array(16)].map((_, i) => i + 1));
});

test('all 16 banked questions round-trip through normalize', () => {
  const seen = new Set();
  for (const a of asks) {
    const n = normalize(a.q);
    assert.ok(n, a.q);
    assert.equal(normalize(n), n, `normalize is stable for ${a.q}`);
    assert.ok(!seen.has(n), `two questions normalise alike: ${a.q}`);
    seen.add(n);
    for (const typed of [a.q, n, a.q.toUpperCase(), `  ${a.q.replace(/[?.]$/, '')}  `, a.q.replace(/'/g, '’')]) {
      const r = bank.ask(typed);
      assert.equal(r.kind, 'banked', typed);
      assert.equal(r.item, a, typed);
    }
  }
});

test('an unbanked question never gets app text back', () => {
  const unbanked = [
    'Why did the backlog get worse?', // a near miss of Q1
    'What day rate did the agency quote?', // Q9, shortened
    'How much has the software renewal gone up by?',
    'What did we decide?',
    'Who is Dana?',
    'Summarise this meeting.',
    'dollars',
    'I found nothing in this meeting that says that.', // an answer is not a question
    '', '?', '   ',
  ];
  for (const q of unbanked) {
    const r = bank.ask(q);
    assert.deepEqual(r, { kind: 'unbanked' }, q);
    const out = JSON.stringify(r);
    for (const s of appText) assert.ok(!out.includes(s), `unbanked "${q}" returned app text`);
  }
});

test('the scoreboard tally comes out as expected', () => {
  assert.deepEqual(tally(demo), {
    lineNo: 4, anchored: 11, linePartly: 7, keptPartly: 4, kept: 12,
    trapsRefused: 8, traps: 8, answerableRefused: 1, answerable: 8, invented: 1,
  });
});

test('the page shows the same numbers the tally counts', () => {
  const t = tally(demo);
  const shown = [...home.matchAll(/<b data-tally="(\w+)">(\d+)<\/b>/g)];
  assert.equal(shown.length, 10, 'every scoreboard number is marked');
  for (const [, key, value] of shown) assert.equal(Number(value), t[key], key);
});

test('refusals are the app\'s own refusal, and only those', () => {
  const refusal = demo.app.chrome.askRefusal;
  assert.deepEqual(asks.filter((a) => a.refused).map((a) => a.n), [3, 9, 10, 11, 12, 13, 14, 15, 16]);
  for (const a of asks) assert.equal(a.refused, a.answer.length === 1 && a.answer[0].text === refusal);
});

test('verdicts are words, not colours', () => {
  const cap = demo.site.captions;
  for (const a of Object.values(demo.site.audit)) assert.match(verdictText(a, cap), /: (yes|partly|no)\b/);
  assert.equal(verdictText({ line: 'no', transcript: 'partly' }, cap), 'Line: no · Transcript: partly');
  assert.equal(verdictText({ line: null, transcript: 'yes' }, cap), 'Transcript: yes');
  assert.equal(verdictText({ verdict: 'no', label: 'Refused, wrongly' }, cap), 'Verdict: no · Refused, wrongly');
});

test('every timestamp points at a transcript line', () => {
  const starts = new Set(demo.app.transcript.map((l) => l.s));
  const stamps = [
    ...demo.app.summary.sections.flatMap((s) => s.items.flatMap((i) => i.sentences.map((x) => x.t))),
    ...asks.flatMap((a) => a.answer.flatMap((s) => s.cites.map((c) => c.t))),
  ];
  for (const t of stamps) assert.ok(starts.has(secondsOf(t)), t);
  assert.equal(secondsOf('3:05'), 185);
  assert.equal(secondsOf('00:57'), 57);
});
