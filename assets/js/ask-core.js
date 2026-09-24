// The FAQ assistant's matching logic. No DOM and no network: ask-ui.js runs it
// in the browser, and tests/ask-core.test.js runs it under node against
// tests/faq-eval.json.
//
// It is retrieval, not generation. It indexes each entry's question, its
// alternative phrasings and its keywords (never the answer), finds the closest
// entry to what was typed, and answers only when three gates all pass:
//   - score:    the best match scores at least gate.minScore;
//   - coverage: at least gate.minCoverage of the question's meaningful words
//               matched that entry;
//   - margin:   the best score is at least gate.minMargin times the runner-up.
// Otherwise it refuses. Nothing is fuzzy-matched; only words of five or more
// letters may match as a prefix ("summar" finds "summary").

import { normalize } from './ask-bank.js';

// normalize() and the demo's bankEngine() live in ask-bank.js, so the home
// page can use them without loading this file; both are re-exported here.
export { bankEngine, normalize } from './ask-bank.js';

// Words that carry no meaning of their own in a question about the product,
// including its name: everyone asking here is asking about Meringo Minutes.
// Negations and "know" are deliberately not here: "What does Ask do when it
// doesn't know?" must not shrink to "ask".
export const STOPWORDS = new Set(`
a about after again all also am an and any anything are as at back be been before being but by
can could did do does each else even ever every for from get gets getting go goes
going got had has have having here how i id if im in into is it its ive just let like me
might mine more most much must my no of off on one only or other our out over own please
really should so some something than that thats the their them then there theres these they
theyre this those to too up us very was we were what whats when where which while who whom
whose why will with would yes yet you your youre yours
tell tells want wants need needs needed use uses using used work works working worked look looks
looking take takes taking add right whole new mean means meaning keep keeps keeping based create mac
between many enough correctly exactly actually whos
say says said
app apps meringo minute minutes meeting meetings hi hello hey thanks thank ok okay
`.trim().split(/\s+/));

export function tokenize(text) {
  const n = normalize(text);
  return n ? n.split(' ') : [];
}

// A light stemmer, so "recordings", "recorded" and "recording" meet at
// "record". British and American spellings meet too ("summarize" ->
// "summarise"). It only has to be consistent: the index and the question go
// through the same function.
// Words the rules below would merge with a different word ("plane" and
// "plan"), kept as they are.
const KEEP = new Set(['plane', 'planes']);

export function stem(term) {
  if (KEEP.has(term)) return term.replace(/s$/, '');
  let t = term.replace(/iz/g, 'is').replace(/yz/g, 'ys');
  if (t.length <= 3 || /^\d/.test(t)) return t;
  if (t.endsWith('ies') && t.length > 4) t = t.slice(0, -3) + 'y';
  else if (t.endsWith('sses')) t = t.slice(0, -2);
  else if (t.endsWith('s') && !/(ss|us|is)$/.test(t)) t = t.slice(0, -1);
  if (t.endsWith('ing') && t.length > 5) t = t.slice(0, -3);
  else if (t.endsWith('ed') && t.length > 4) t = t.slice(0, -2);
  if (t.endsWith('e') && t.length > 3) t = t.slice(0, -1);
  return t;
}

// null drops the term, as MiniSearch expects.
export function processTerm(term) {
  // A bare number ("Windows 10", "8 GB") never decides what a question is about.
  if (!term || STOPWORDS.has(term) || /^\d+$/.test(term)) return null;
  return stem(term);
}

// The question's meaningful terms, once each.
export function queryTerms(text) {
  return [...new Set(tokenize(text).map(processTerm).filter(Boolean))];
}

const joinField = (doc, field) => {
  const v = doc[field];
  return Array.isArray(v) ? v.join(' . ') : (v ?? '');
};

export const SEARCH_OPTIONS = Object.freeze({
  fields: ['q', 'alt', 'keywords'],
  boost: { q: 3, alt: 1.5, keywords: 1 },
});

export function faqEngine(faqData, MiniSearch) {
  const entries = faqData.entries;
  const gate = { minScore: 4, minCoverage: 0.6, minMargin: 1.15, ...faqData.gate };
  const byId = new Map(entries.map((e) => [e.id, e]));
  const index = new MiniSearch({
    idField: 'id',
    fields: SEARCH_OPTIONS.fields, // never the answer
    storeFields: [],
    extractField: joinField,
    tokenize,
    processTerm,
    searchOptions: {
      boost: SEARCH_OPTIONS.boost,
      fuzzy: false,
      prefix: (term) => term.length >= 5,
      combineWith: 'OR',
      tokenize,
      processTerm,
    },
  });
  index.addAll(entries);

  function rank(question) {
    return index.search(question);
  }

  function ask(question) {
    const terms = queryTerms(question);
    if (!terms.length) return { kind: 'refuse', best: null };
    const results = rank(question);
    if (!results.length) return { kind: 'refuse', best: null };
    const [top, second] = results;
    const matched = new Set(top.queryTerms);
    const coverage = terms.filter((t) => matched.has(t)).length / terms.length;
    const runnerUp = second ? { id: second.id, score: second.score } : null;
    const margin = second ? top.score / second.score : Infinity;
    const best = { id: top.id, entry: byId.get(top.id), score: top.score, coverage, margin, runnerUp };
    const failed = [];
    if (top.score < gate.minScore) failed.push('score');
    if (coverage < gate.minCoverage) failed.push('coverage');
    if (margin < gate.minMargin) failed.push('margin');
    if (failed.length) return { kind: 'refuse', best: { ...best, failed } };
    return { kind: 'answer', entry: best.entry, score: top.score, runnerUp, coverage };
  }

  return { ask, rank, gate, terms: queryTerms };
}

// An answer is plain text in which a link is written [text](/path/). This
// splits it into text and link parts for the page to render; only
// root-relative paths become links.
export function answerParts(answer) {
  const parts = [];
  const rx = /\[([^\]]+)\]\((\/[^)\s]*)\)/g;
  let last = 0;
  for (const m of String(answer).matchAll(rx)) {
    if (m.index > last) parts.push({ text: answer.slice(last, m.index) });
    parts.push({ text: m[1], href: m[2] });
    last = m.index + m[0].length;
  }
  if (last < answer.length) parts.push({ text: answer.slice(last) });
  return parts;
}

export function answerText(answer) {
  return answerParts(answer).map((p) => p.text).join('');
}
