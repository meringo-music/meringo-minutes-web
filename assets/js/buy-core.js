// What /buy/ sells, and from which Paddle account. No DOM, shared by buy.js
// and the node tests. Paddle's script is the one thing this site loads from
// another origin, and only buy.js loads it: on /buy/, after a buyer has
// accepted the terms and pressed Buy.

export const PADDLE_JS = 'https://cdn.paddle.com/paddle/v2/paddle.js';

// Client-side tokens are public by design: Paddle.js needs one in the page,
// and it can open a checkout but read nothing. Price ids are Paddle's.
export const ACCOUNTS = {
  // Paddle's sandbox, for buying with the test card on this machine
  // (python -m http.server 8099 --bind 127.0.0.1).
  sandbox: {
    token: 'test_e6fff7f5bf5e1f78c726c4981f6',
    prices: { launch: 'pri_01m4byxdc5re3bgx79djmy4adz', live: 'pri_01m4byxdc5re3bgx79djmy4adz' },
  },
  // meringominutes.app. The live token arrives with the launch-state change.
  production: {
    token: null,
    prices: { launch: 'pri_01m4c5z4fbhgthrarkqwx5mfja', live: 'pri_01m4c614r50dt5f0mc1jbz0es3' },
  },
};

const LOCAL = new Set(['127.0.0.1', 'localhost', '[::1]']);

export function environment(hostname) {
  if (hostname === 'meringominutes.app') return 'production';
  if (LOCAL.has(hostname)) return 'sandbox';
  return null;
}

// What Buy opens on this host in this launch state, or null when nothing is
// for sale here. The live site sells nothing before launch; the sandbox sells
// in any state, so the checkout can be tried before it is.
export function offer(hostname, state, accounts = ACCOUNTS) {
  const env = environment(hostname);
  if (!env) return null;
  if (env === 'production' && state !== 'launch' && state !== 'live') return null;
  const account = accounts[env];
  if (!account.token) return null;
  return { env, token: account.token, priceId: account.prices[state === 'live' ? 'live' : 'launch'] };
}

// Paddle's payment links come back to this page as ?_ptxn=txn_…
export function transactionFrom(search) {
  const id = new URLSearchParams(search).get('_ptxn');
  return id && /^txn_[a-z0-9]+$/.test(id) ? id : null;
}

// Settings every checkout opens with, a payment link's included.
export function checkoutSettings(theme) {
  return { displayMode: 'overlay', theme: theme === 'dark' ? 'dark' : 'light', locale: 'en', showAddDiscounts: false };
}

// One licence for one Mac, so always a quantity of one. The terms the buyer
// accepted ride along on the transaction, named by their "Last updated" date.
export function checkoutRequest(priceId, termsVersion) {
  return { items: [{ priceId, quantity: 1 }], customData: { terms_accepted: termsVersion } };
}
