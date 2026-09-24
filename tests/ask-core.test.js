import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import MiniSearch from '../assets/vendor/minisearch-7.1.2.js';
import {
  answerParts, answerText, bankEngine, faqEngine, normalize, processTerm, queryTerms, stem,
} from '../assets/js/ask-core.js';

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const faq = read('../assets/data/faq.json');
const evalSet = read('./faq-eval.json');
const engine = faqEngine(faq, MiniSearch);

const isRight = (expect, id) => (Array.isArray(expect) ? expect.includes(id) : expect === id);

function run(items) {
  const out = { right: 0, refused: 0, wrong: [], total: items.length };
  for (const item of items) {
    const r = engine.ask(item.q);
    const got = r.kind === 'answer' ? r.entry.id : null;
    if (got === null) out.refused++;
    else if (isRight(item.expect, got)) out.right++;
    else out.wrong.push(`${item.q} -> ${got} (expected ${item.expect ?? 'a refusal'})`);
  }
  return out;
}

test('normalize folds case, accents, apostrophes and punctuation', () => {
  assert.equal(normalize('  Doesn’t it WORK — offline?! '), 'doesnt it work offline');
  assert.equal(normalize('Résumé, café'), 'resume cafe');
  assert.equal(normalize('16GB of RAM'), '16 gb of ram');
  assert.equal(normalize(null), '');
});

test('stems meet across inflections and spellings, and stopwords drop out', () => {
  assert.equal(stem('recordings'), stem('recording'));
  assert.equal(stem('recorded'), stem('record'));
  assert.equal(stem('summarize'), stem('summarise'));
  assert.equal(stem('shared'), stem('share'));
  assert.notEqual(stem('plane'), stem('plan'));
  assert.equal(processTerm('the'), null);
  assert.equal(processTerm('meringo'), null);
  assert.equal(processTerm('2019'), null);
  assert.deepEqual(queryTerms('Does Meringo Minutes work offline?'), [stem('offline')]);
  assert.ok(queryTerms("What does Ask do when it doesn't know?").includes('know'));
});

test('faq.json has the shape the page and the assistant rely on', () => {
  assert.equal(faq.disclosure, "Automated answers from this site's FAQ — not a person.");
  assert.equal(faq.refusal, 'I found nothing on this site that says that.');
  for (const k of ['minScore', 'minCoverage', 'minMargin']) assert.equal(typeof faq.gate[k], 'number', k);
  const ids = new Set();
  const groups = new Set(faq.groups.map((g) => g.id));
  for (const e of faq.entries) {
    assert.ok(!ids.has(e.id), `duplicate id ${e.id}`);
    ids.add(e.id);
    for (const k of ['id', 'q', 'answer', 'group', 'asOf']) assert.ok(e[k], `${e.id} has no ${k}`);
    for (const k of ['alt', 'keywords', 'facts', 'sources']) assert.ok(Array.isArray(e[k]), `${e.id}.${k}`);
    assert.ok(groups.has(e.group), `${e.id} group ${e.group}`);
    assert.ok(e.sources.length, `${e.id} has no sources`);
    assert.doesNotMatch(e.answer, /\[[^\]]*\](?!\()/, `${e.id} still carries a source tag`);
  }
  assert.ok(!ids.has('f42'), 'F42 (refunds) is launch-only');
});

test('the index never holds answer text', () => {
  // Words that appear only in answers find nothing.
  for (const word of ['Pemberton', 'gag', 'Erie', 'Unannounced']) {
    assert.deepEqual(engine.rank(word), [], word);
  }
});

test('an answer carries its entry, score, runner-up and coverage', () => {
  const r = engine.ask('Does it work offline?');
  assert.equal(r.kind, 'answer');
  assert.equal(r.entry.id, 'f01');
  assert.equal(typeof r.score, 'number');
  assert.equal(r.coverage, 1);
  assert.ok(r.runnerUp === null || typeof r.runnerUp.score === 'number');
});

test('a refusal carries the best candidate and the gates it failed', () => {
  const r = engine.ask('How do I cancel my subscription');
  assert.equal(r.kind, 'refuse');
  assert.equal(r.best.id, 'f39');
  assert.deepEqual(r.best.failed, ['coverage']);
  assert.deepEqual(engine.ask('What is the weather'), { kind: 'refuse', best: null });
  assert.deepEqual(engine.ask('?!'), { kind: 'refuse', best: null });
});

for (const [bucket, items] of Object.entries(evalSet.buckets)) {
  test(`eval: ${bucket}`, () => {
    const r = run(items);
    const gate = evalSet.gates[bucket];
    const expectRefusal = items.every((i) => i.expect === null);
    const rate = (expectRefusal ? r.refused : r.right) / r.total;
    console.log(`  ${bucket}: ${expectRefusal ? `refused ${r.refused}` : `answered right ${r.right}`} of ${r.total} (${(rate * 100).toFixed(0)}%), wrong ${r.wrong.length}`);
    assert.deepEqual(r.wrong, [], `${bucket}: wrong answers`);
    if (gate != null) assert.ok(rate >= gate, `${bucket}: ${(rate * 100).toFixed(1)}% is under ${gate * 100}%`);
  });
}

test('the exact bucket is every entry\'s own question', () => {
  const exact = new Set(evalSet.buckets.exact.map((i) => i.q));
  for (const e of faq.entries) assert.ok(exact.has(e.q), e.q);
});

test('paraphrases are not copied from the alt phrasings', () => {
  const alts = new Set(faq.entries.flatMap((e) => e.alt).map(normalize));
  for (const [bucket, items] of Object.entries(evalSet.buckets)) {
    if (!bucket.startsWith('paraphrase')) continue;
    for (const i of items) assert.ok(!alts.has(normalize(i.q)), i.q);
  }
  assert.ok(evalSet.buckets.paraphrase.length >= 30);
  assert.ok(evalSet.buckets['out-of-scope'].length >= 25);
});

test('answers split into text and root-relative links only', () => {
  assert.deepEqual(answerParts('See [the privacy page](/privacy/) now.'), [
    { text: 'See ' }, { text: 'the privacy page', href: '/privacy/' }, { text: ' now.' },
  ]);
  assert.deepEqual(answerParts('[x](https://example.com)'), [{ text: '[x](https://example.com)' }]);
  assert.equal(answerText('[The privacy page](/privacy/) has the details.'), 'The privacy page has the details.');
});

test('bankEngine answers only questions it was given, after normalising', () => {
  const bank = bankEngine({ questions: [{ q: "What's Dana's day rate?", a: 'x' }] });
  assert.equal(bank.ask('whats danas day rate').kind, 'banked');
  assert.equal(bank.ask("What is Dana's day rate?").kind, 'unbanked');
  assert.equal(bankEngine().ask('anything').kind, 'unbanked');
});
