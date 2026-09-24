// Site behaviour shared by every page. Loaded as a module, so it runs after
// the document is parsed. Nothing here talks to the network.

import { isCurrent } from './nav.js';
import { label, nextChoice, normalizeChoice, sourceMedia } from './theme.js';
import './visit.js';

const KEY = 'theme';

function readChoice() {
  try { return normalizeChoice(localStorage.getItem(KEY)); } catch { return 'system'; }
}

function saveChoice(choice) {
  try {
    if (choice === 'system') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch { /* storage blocked: the choice lasts for this page only */ }
}

function applyChoice(choice) {
  const root = document.documentElement;
  if (choice === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', choice);

  // Pictures and the browser chrome colour follow the choice, not only the OS.
  for (const el of document.querySelectorAll('picture source[media], meta[name="theme-color"][media]')) {
    if (!el.dataset.media) el.dataset.media = el.getAttribute('media');
    el.setAttribute('media', sourceMedia(el.dataset.media, choice));
  }

  for (const button of document.querySelectorAll('[data-theme-toggle]')) {
    button.dataset.choice = choice;
    button.setAttribute('aria-label', label(choice));
    button.title = label(choice);
  }
}

function setupThemeToggle() {
  let choice = readChoice();
  applyChoice(choice);
  for (const button of document.querySelectorAll('[data-theme-toggle]')) {
    button.hidden = false;
    button.addEventListener('click', () => {
      choice = nextChoice(choice);
      saveChoice(choice);
      applyChoice(choice);
    });
  }
}

// Marked here, not in the HTML, so aria-current stays out of /privacy/'s
// source, which the desk's page renderer copies onto other pages.
function markCurrentPage() {
  for (const link of document.querySelectorAll('.site-nav a[href]')) {
    if (isCurrent(link.getAttribute('href'), location.pathname)) link.setAttribute('aria-current', 'page');
  }
}

setupThemeToggle();
markCurrentPage();
