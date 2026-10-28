#!/usr/bin/env node
/* Render the social card and the social video from site/og.html.

     node site/tools/og.mjs              # og.png, og-fa.png, og.mp4, og-fa.mp4
     node site/tools/og.mjs png          # stills only
     node site/tools/og.mjs mp4 --fps 30 # video only, at another frame rate

   og.html draws any instant exactly (window.__render(t)), so the video is
   captured frame by frame, not screen-recorded: each frame is rendered at 2×,
   piped to ffmpeg, and downsampled to 1200×630 with Lanczos. H.264, yuv420p,
   faststart, so every player and every link preview can show it. Needs ffmpeg
   and a Chrome (Google Chrome, or Playwright's Chromium). Not published. */
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync, mkdtempSync, readdirSync, statSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join, extname, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const what = args.find(a => a === 'png' || a === 'mp4') || 'all';
const FPS = +(args[args.indexOf('--fps') + 1] || 0) || 60;
const STILL_T = 4.3;          // ledger-api waiting on you, the badge up in the menu bar
const SCALE = 2;

function chrome() {
  const c = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
  const pw = join(homedir(), 'Library/Caches/ms-playwright');
  if (existsSync(pw)) for (const d of readdirSync(pw).filter(d => d.startsWith('chromium-')).sort().reverse())
    c.push(join(pw, d, 'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
           join(pw, d, 'chrome-linux/chrome'));
  const hit = c.find(p => existsSync(p));
  if (!hit) throw new Error('no Chrome found');
  return hit;
}

const TYPES = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png' };
const server = createServer(async (q, r) => {
  try { const p = join(SITE, decodeURIComponent(new URL(q.url, 'http://x').pathname));
    if (!p.startsWith(SITE)) throw 0;
    const body = await readFile(p);
    r.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' }); r.end(body); }
  catch { if (!r.headersSent) r.writeHead(404); r.end(); }
});
await new Promise(ok => server.listen(0, '127.0.0.1', ok));
const base = `http://127.0.0.1:${server.address().port}/og.html`;

const port = 9600 + Math.floor(Math.random() * 300);
const proc = spawn(chrome(), ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'og-'))}`,
  '--hide-scrollbars', '--no-first-run', '--force-color-profile=srgb', '--window-size=1200,630', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let list = [];
for (let i = 0; i < 80 && !list.length; i++) { try { list = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).filter(x => x.type === 'page'); } catch { } await sleep(150); }
if (!list.length) { proc.kill(); server.close(); throw new Error('Chrome did not start'); }
const ws = new WebSocket(list[0].webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map();
ws.onmessage = m => { const d = JSON.parse(m.data);
  if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
  if (d.method === 'Runtime.exceptionThrown') console.error('page error:', d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text); };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async expr => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send('Runtime.enable'); await send('Page.enable');

async function open(query, scale) {
  await send('Emulation.setDeviceMetricsOverride', { width: 1200, height: 630, deviceScaleFactor: scale, mobile: false });
  await send('Page.navigate', { url: base + query });
  for (let i = 0; i < 100 && !(await evaluate('window.__ready===true')); i++) await sleep(50);
  await evaluate('document.fonts.ready.then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
  /* og.html is styled by app.css: a card rendered without it must not ship */
  if (!(await evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sans').trim()")))
    throw new Error('og.html rendered without app.css (check the MIME types above)');
}
const shot = async () => Buffer.from((await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 1200, height: 630, scale: 1 } })).result.data, 'base64');

async function still(lang, out) {
  await open(`?t=${STILL_T}&cap=0${lang ? '&lang=' + lang : ''}`, 1);
  const { writeFile } = await import('node:fs/promises');
  await writeFile(join(SITE, out), await shot());
  console.log('→', out);
}

async function video(lang, out) {
  await open(`?capture=1${lang ? '&lang=' + lang : ''}`, SCALE);
  const T = await evaluate('window.__T'), n = Math.round(T * FPS);
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
    '-vf', 'scale=1200:630:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20',
    '-profile:v', 'high', '-tune', 'animation', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', join(SITE, out)],
    { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((ok, no) => ff.on('close', c => c ? no(new Error('ffmpeg ' + c)) : ok()));
  for (let f = 0; f < n; f++) {
    await evaluate(`window.__render(${(f / FPS).toFixed(6)})`);
    const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).result.data, 'base64');
    if (!ff.stdin.write(png)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % FPS === 0) process.stdout.write(`\r${out}  ${(f / FPS).toFixed(0)}s / ${T}s`);
  }
  ff.stdin.end(); await done;
  console.log(`\r→ ${out}  ${n} frames, ${(statSync(join(SITE, out)).size / 1e6).toFixed(2)} MB`);
}

try {
  if (what !== 'mp4') { await still('', 'og.png'); await still('fa', 'og-fa.png'); }
  if (what !== 'png') { await video('', 'og.mp4'); await video('fa', 'og-fa.mp4'); }
} finally { ws.close(); proc.kill(); server.close(); }
