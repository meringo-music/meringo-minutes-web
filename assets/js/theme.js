// Theme logic, no DOM. The choice cycles System → Light → Dark; "System"
// follows prefers-color-scheme, the other two override it.

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

// A <source media="(prefers-color-scheme: …)"> follows the OS, not the toggle:
// an override rewrites it to 'all' or 'not all', and 'system' puts it back.
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
