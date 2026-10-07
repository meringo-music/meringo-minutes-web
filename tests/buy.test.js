import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ACCOUNTS, checkoutRequest, checkoutSettings, environment, offer, transactionFrom } from '../assets/js/buy-core.js';

const withTokens = {
  sandbox: { ...ACCOUNTS.sandbox, token: 'test_sandbox' },
  production: { ...ACCOUNTS.production, token: 'live_production' },
};

test('the live site talks to the live account, this machine to the sandbox, anywhere else to neither', () => {
  assert.equal(environment('meringominutes.app'), 'production');
  for (const host of ['127.0.0.1', 'localhost', '[::1]']) assert.equal(environment(host), 'sandbox', host);
  for (const host of ['www.meringominutes.app', 'meringo-music.github.io', 'example.com']) assert.equal(environment(host), null, host);
});

test('the live site sells nothing before launch', () => {
  assert.equal(offer('meringominutes.app', 'prelaunch', withTokens), null);
  assert.equal(offer('meringominutes.app', undefined, withTokens), null);
});

test('the launch price until the site goes live, then the list price', () => {
  assert.equal(offer('meringominutes.app', 'launch', withTokens).priceId, ACCOUNTS.production.prices.launch);
  assert.equal(offer('meringominutes.app', 'live', withTokens).priceId, ACCOUNTS.production.prices.live);
  assert.notEqual(ACCOUNTS.production.prices.launch, ACCOUNTS.production.prices.live);
});

test('the sandbox sells in any state, so the checkout can be tried before launch', () => {
  const sale = offer('127.0.0.1', 'prelaunch', withTokens);
  assert.deepEqual(sale, { env: 'sandbox', token: 'test_sandbox', priceId: ACCOUNTS.sandbox.prices.launch });
});

test('no token, no sale', () => {
  const none = { sandbox: { ...ACCOUNTS.sandbox, token: null }, production: { ...ACCOUNTS.production, token: null } };
  assert.equal(offer('127.0.0.1', 'prelaunch', none), null);
  assert.equal(offer('meringominutes.app', 'launch', none), null);
});

test('each account uses its own kind of token', () => {
  if (ACCOUNTS.sandbox.token) assert.match(ACCOUNTS.sandbox.token, /^test_/);
  if (ACCOUNTS.production.token) assert.match(ACCOUNTS.production.token, /^live_/);
});

test('one licence per checkout, and the accepted terms go with it', () => {
  assert.deepEqual(checkoutRequest('pri_x', '2026-10-07'), {
    items: [{ priceId: 'pri_x', quantity: 1 }],
    customData: { terms_accepted: '2026-10-07' },
  });
});

test('a payment link is read from ?_ptxn= and nothing else', () => {
  assert.equal(transactionFrom('?_ptxn=txn_01abc'), 'txn_01abc');
  assert.equal(transactionFrom('?x=1&_ptxn=txn_01abc'), 'txn_01abc');
  assert.equal(transactionFrom(''), null);
  assert.equal(transactionFrom('?_ptxn=javascript:alert(1)'), null);
  assert.equal(transactionFrom('?_ptxn=pri_01abc'), null);
});

test('the checkout follows the page theme and hides the discount box', () => {
  assert.equal(checkoutSettings('dark').theme, 'dark');
  assert.equal(checkoutSettings('light').theme, 'light');
  assert.equal(checkoutSettings('anything').theme, 'light');
  assert.equal(checkoutSettings('dark').showAddDiscounts, false);
  assert.equal(checkoutSettings('dark').displayMode, 'overlay');
});
