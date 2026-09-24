import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isCurrent, normalizePath } from '../assets/js/nav.js';

test('a page is current however its address is written', () => {
  for (const p of ['/privacy/', '/privacy', '/privacy/index.html', '/privacy/?x=1', '/privacy/#voices']) {
    assert.equal(isCurrent('/privacy/', p), true, p);
  }
});

test('other pages are not current', () => {
  assert.equal(isCurrent('/privacy/', '/'), false);
  assert.equal(isCurrent('/privacy/', '/download/'), false);
  assert.equal(isCurrent('/how-it-works/', '/how-it-works/privacy/'), false);
});

test('the home page and files keep their own shape', () => {
  assert.equal(normalizePath(''), '/');
  assert.equal(normalizePath('/index.html'), '/');
  assert.equal(normalizePath('/404.html'), '/404.html');
  assert.equal(isCurrent('/', '/'), true);
});
