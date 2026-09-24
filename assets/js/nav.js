// Which header link is the page being viewed. No DOM, shared by site.js and
// the node tests. The header is one shared partial, so the current page is
// marked at runtime rather than in each page's HTML.

export function normalizePath(path) {
  let p = String(path || '/').split(/[?#]/)[0] || '/';
  p = p.replace(/\/index\.html$/, '/');
  if (!p.endsWith('/') && !/\.[a-z0-9]+$/i.test(p.split('/').pop())) p += '/';
  return p;
}

export function isCurrent(href, pathname) {
  return normalizePath(href) === normalizePath(pathname);
}
