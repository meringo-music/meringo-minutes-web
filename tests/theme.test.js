import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CHOICES, label, nextChoice, normalizeChoice, resolveTheme, sourceMedia } from '../assets/js/theme.js';

test('the toggle cycles system → light → dark → system', () => {
  assert.equal(nextChoice('system'), 'light');
  assert.equal(nextChoice('light'), 'dark');
  assert.equal(nextChoice('dark'), 'system');
});

test('anything unexpected in storage is treated as system', () => {
  for (const junk of [null, undefined, '', 'auto', 'DARK', 42]) {
    assert.equal(normalizeChoice(junk), 'system');
    assert.equal(nextChoice(junk), 'light');
  }
});

test('system follows the OS; light and dark override it', () => {
  assert.equal(resolveTheme('system', true), 'dark');
  assert.equal(resolveTheme('system', false), 'light');
  assert.equal(resolveTheme('light', true), 'light');
  assert.equal(resolveTheme('dark', false), 'dark');
});

test('picture sources follow an override and restore on system', () => {
  const dark = '(prefers-color-scheme: dark)';
  const light = '(prefers-color-scheme: light)';
  assert.equal(sourceMedia(dark, 'dark'), 'all');
  assert.equal(sourceMedia(dark, 'light'), 'not all');
  assert.equal(sourceMedia(light, 'light'), 'all');
  assert.equal(sourceMedia(light, 'dark'), 'not all');
  assert.equal(sourceMedia(dark, 'system'), dark);
  assert.equal(sourceMedia('(min-width: 800px)', 'dark'), '(min-width: 800px)');
});

test('every choice has a label that names it', () => {
  for (const c of CHOICES) assert.match(label(c), /^Theme: /);
  assert.equal(new Set(CHOICES.map(label)).size, CHOICES.length);
});
