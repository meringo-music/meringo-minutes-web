// /buy/: the terms box unlocks Buy, and Buy loads Paddle's checkout. This is
// the only code on the site that loads anything from another origin, and it
// does so only after that press (/privacy/, "This site").

import { PADDLE_JS, checkoutRequest, checkoutSettings, offer, transactionFrom } from './buy-core.js';

const card = document.querySelector('[data-buy]');
const sale = card && offer(location.hostname, document.body.dataset.ctaState);

function part(name) {
  return card.querySelector(`[data-buy-${name}]`);
}

function theme() {
  const chosen = document.documentElement.getAttribute('data-theme');
  if (chosen) return chosen;
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function loadPaddle() {
  if (window.Paddle) return Promise.resolve(window.Paddle);
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = PADDLE_JS;
    script.onload = () => (window.Paddle ? resolve(window.Paddle) : reject(new Error('no Paddle')));
    script.onerror = () => reject(new Error('Paddle.js did not load'));
    document.head.append(script);
  });
}

function setup() {
  const open = part('open');
  const box = part('terms');
  const button = part('button');
  const error = part('error');
  const done = part('done');
  const transaction = transactionFrom(location.search);
  let started = false;

  part('closed').hidden = true;
  open.hidden = false;
  box.addEventListener('change', () => { button.disabled = !box.checked; });

  function onEvent(event) {
    if (event.name === 'checkout.completed') {
      open.hidden = true;
      done.hidden = false;
    } else if (event.name === 'checkout.closed') {
      button.disabled = !box.checked;
    }
  }

  button.addEventListener('click', async () => {
    if (!box.checked) return;
    button.disabled = true;
    error.hidden = true;
    let Paddle;
    try {
      Paddle = await loadPaddle();
    } catch {
      error.hidden = false;
      button.disabled = false;
      return;
    }
    if (!started) {
      started = true;
      if (sale.env === 'sandbox') Paddle.Environment.set('sandbox');
      // A payment link's checkout opens itself here, from ?_ptxn= (Paddle's
      // default payment link); anything else opens below.
      Paddle.Initialize({ token: sale.token, checkout: { settings: checkoutSettings(theme()) }, eventCallback: onEvent });
      if (transaction) return;
    }
    Paddle.Checkout.open({
      ...(transaction ? { transactionId: transaction } : checkoutRequest(sale.priceId, card.dataset.termsVersion)),
      settings: checkoutSettings(theme()),
    });
  });
}

if (sale) setup();
