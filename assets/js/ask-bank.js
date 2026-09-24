// normalize() and the demo's bank, apart from the FAQ engine (ask-core.js).

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

// Only the questions the app was asked, matched exactly after normalising;
// anything else is "unbanked" and carries nothing from the bank.
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
