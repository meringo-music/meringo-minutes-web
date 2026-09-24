// Screenshots the site at real device widths, in both themes, and reports
// horizontal overflow. Headless Edge will not size a window below ~500 px,
// so this drives it over the DevTools protocol and emulates the device.
//
//   python -m http.server 8099 --bind 127.0.0.1      (in the repo root)
//   node tools/shoot.mjs [out-dir] [path ...]
//
// Writes <out>/<page>-<width>-<theme>.png and exits 1 if any page scrolls
// sideways at any width. Needs Node 22+ (global WebSocket) and Microsoft Edge.

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EDGE = process.env.EDGE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const out = process.argv[2] || 'shots';
const paths = process.argv.slice(3).length ? process.argv.slice(3) : ['/'];
const WIDTHS = (process.env.WIDTHS || "390,768,1280").split(",").map(Number);
const THEMES = ['light', 'dark'];
const PORT = 9333;

mkdirSync(out, { recursive: true });
const profile = mkdtempSync(join(tmpdir(), 'shoot-'));
// --no-proxy-server: a filtering proxy on the machine can rewrite pages on
// their way to the browser (one injected a dark-mode stylesheet into about
// half the light-theme shots), so a screenshot would show its styles, not ours.
const edge = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-proxy-server', '--hide-scrollbars',
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error('Edge did not start');
}

const ws = new WebSocket(await target());
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0;
const pending = new Map();
const waiters = [];
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  if (msg.method) for (const w of waiters.splice(0)) w(msg);
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const n = ++id;
  pending.set(n, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result)));
  ws.send(JSON.stringify({ id: n, method, params }));
});
const loaded = () => new Promise((resolve) => {
  const check = (m) => (m.method === 'Page.loadEventFired' ? resolve() : waiters.push(check));
  waiters.push(check);
});

await send('Page.enable');
let overflow = 0;
for (const path of paths) {
  for (const width of WIDTHS) {
    for (const theme of THEMES) {
      await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: theme }] });
      await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 700 });
      const done = loaded();
      await send('Page.navigate', { url: BASE + path });
      await done;
      await sleep(400);
      const { result } = await send('Runtime.evaluate', {
        expression: 'JSON.stringify({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, h: document.documentElement.scrollHeight, bg: getComputedStyle(document.body).backgroundColor, dark: matchMedia("(prefers-color-scheme: dark)").matches})',
        returnByValue: true,
      });
      const m = JSON.parse(result.value);
      if (process.env.VERBOSE) console.log(path, width, theme, m.bg, 'dark=' + m.dark);
      if (m.sw > m.cw) { overflow++; console.log(`OVERFLOW ${path} @${width} ${theme}: scrollWidth ${m.sw} > ${m.cw}`); }
      await send('Emulation.setDeviceMetricsOverride', { width, height: Math.min(m.h, 6000), deviceScaleFactor: 1, mobile: width < 700 });
      await sleep(500); // let the resized page repaint before capture
      const shot = await send('Page.captureScreenshot', { format: 'png' });
      const name = (path.replace(/\/+/g, '-').replace(/^-|-$/g, '') || 'home') + `-${width}-${theme}.png`;
      writeFileSync(join(out, name), Buffer.from(shot.data, 'base64'));
    }
  }
}
ws.close();
edge.kill();
console.log(`${paths.length * WIDTHS.length * THEMES.length} screenshot(s) in ${out}; ${overflow ? overflow + ' overflow(s)' : 'no horizontal overflow'}.`);
process.exit(overflow ? 1 : 0);
