// normalize() and the home page demo's bank: no DOM and no search index, so
// the home page never loads the FAQ engine. ask-core.js re-exports both.

// Lower case, accents off, apostrophes joined ("doesn't" -> "doesnt"), every
// other mark a space. The same function prepares the index and the question.
export function normalize(text) {
  return String(text ?? '')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[‘’ʼ'`´]/g, '')
    .replace(/(\d)([a-z])/g, '$1 $2') // "16gb" -> "16 gb"
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

// The demo answers only the questions the app was actually asked, matched
// exactly after normalising, and never searches: anything else is "unbanked",
// and an unbanked result carries nothing from the bank.
export function bankEngine(bank) {
  const items = new Map();
  for (const item of bank?.questions ?? []) items.set(normalize(item.q), item);
  return {
    ask(question) {
      const item = items.get(normalize(question));
      return item ? { kind: 'banked', item } : { kind: 'unbanked' };
    },
  };
}
