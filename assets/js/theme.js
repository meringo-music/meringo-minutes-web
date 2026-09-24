// Theme logic with no DOM, shared by site.js and the node tests.
// The visitor's choice cycles System → Light → Dark. "System" follows
// prefers-color-scheme; the other two override it.

export const CHOICES = ['system', 'light', 'dark'];

export function normalizeChoice(value) {
  return value === 'light' || value === 'dark' ? value : 'system';
}

export function nextChoice(choice) {
  const i = CHOICES.indexOf(normalizeChoice(choice));
  return CHOICES[(i + 1) % CHOICES.length];
}

export function resolveTheme(choice, systemDark) {
  const c = normalizeChoice(choice);
  if (c !== 'system') return c;
  return systemDark ? 'dark' : 'light';
}

// A <source media="(prefers-color-scheme: dark)"> follows the operating
// system, not the site's toggle. When the visitor overrides the theme, the
// media query is rewritten to 'all' or 'not all'; on 'system' it goes back.
export function sourceMedia(original, choice) {
  const c = normalizeChoice(choice);
  if (c === 'system' || !/prefers-color-scheme/.test(original)) return original;
  const forDark = /prefers-color-scheme:\s*dark/.test(original);
  return forDark === (c === 'dark') ? 'all' : 'not all';
}

export function label(choice) {
  return {
    system: 'Theme: match system',
    light: 'Theme: light',
    dark: 'Theme: dark',
  }[normalizeChoice(choice)];
}
