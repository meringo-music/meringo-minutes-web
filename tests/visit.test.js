import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { clock, formatVisit, pageName } from '../assets/js/visit-format.js';

test('times are m:ss since the page loaded', () => {
  assert.equal(clock(0), '0:00');
  assert.equal(clock(999), '0:00');
  assert.equal(clock(61_500), '1:01');
  assert.equal(clock(600_000), '10:00');
  assert.equal(clock(-5), '0:00');
  assert.equal(clock('junk'), '0:00');
});

test('the home page is named, other pages by their path', () => {
  assert.equal(pageName('/'), 'the home page');
  assert.equal(pageName('/index.html'), 'the home page');
  assert.equal(pageName('/faq/'), '/faq/');
});

test('a visit reads in time order, with the header counting its lines', () => {
  const v = formatVisit([
    [0, 'arrive', '/'],
    [12_400, 'section', 'What Meringo Minutes made of\n   one meeting'],
    [30_000, 'chip', 'What day rate did the agency quote for the locum?'],
    [31_000, 'ts', '1:33'],
    [40_000, 'audit', true],
    [45_000, 'audit', false],
    [50_000, 'script'],
    [60_000, 'theme-toggle', 'dark'],
    [65_000, 'hat'],
  ]);
  assert.equal(v.header, 'All 9 lines traced to this visit');
  assert.deepEqual(v.lines.map((l) => l.t), ['0:00', '0:12', '0:30', '0:31', '0:40', '0:45', '0:50', '1:00', '1:05']);
  assert.deepEqual(v.lines.map((l) => l.text), [
    'You arrived at the home page.',
    'You reached “What Meringo Minutes made of one meeting”.',
    'You asked the demo: “What day rate did the agency quote for the locum?”',
    'You played the recording from 1:33.',
    'You turned on the audit.',
    'You turned the audit off again.',
    'You opened “What was actually said”.',
    'You switched to the dark theme.',
    'You pressed the hat three times.',
  ]);
});

test('FAQ questions become one counted line, at the last one, and never their words', () => {
  const one = formatVisit([[0, 'arrive', '/faq/'], [5_000, 'faq'], [9_000, 'hat']]);
  assert.deepEqual(one.lines[1], { t: '0:05', text: 'You asked the FAQ box 1 question. I kept the count, not the words.' });
  const three = formatVisit([[0, 'arrive', '/faq/'], [5_000, 'faq', 'is it encrypted'], [7_000, 'faq'], [8_000, 'faq'], [9_000, 'hat']]);
  assert.equal(three.lines.length, 3);
  assert.deepEqual(three.lines[1], { t: '0:08', text: 'You asked the FAQ box 3 questions. I kept the count, not the words.' });
  assert.ok(!JSON.stringify(three).includes('encrypted'), 'a value on a FAQ event is never shown');
});

test('unknown, empty or malformed events are left out', () => {
  const v = formatVisit([[0, 'arrive', '/'], [1, 'typed', 'secret'], [2, 'section', '   '], [3, 'theme-toggle', 'normal'], 'junk', null, [4, 'hat']]);
  assert.deepEqual(v.lines.map((l) => l.text), ['You arrived at the home page.', 'You pressed the hat three times.']);
  assert.equal(formatVisit(undefined).header, 'All 0 lines traced to this visit');
});

test('the recorder stays in memory: no storage, no network, no typed values', () => {
  const src = readFileSync(new URL('../assets/js/visit.js', import.meta.url), 'utf8');
  for (const banned of ['localStorage', 'sessionStorage', 'indexedDB', 'cookie', 'fetch(', 'sendBeacon', 'XMLHttpRequest', 'WebSocket', '.value)', 'value,']) {
    assert.ok(!src.includes(banned), `visit.js must not use ${banned}`);
  }
  assert.match(src, /import\('\.\/visit-dialog\.js'\)/, 'the dialog loads only on demand');
});
