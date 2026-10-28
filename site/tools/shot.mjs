// Look at the page headless and hear its errors. Usage:
// node shot.mjs URL OUTDIR "sel1,sel2,..." [WxH] [ground] [waitMs]
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [url, out, sels = 'top', size = '1440x900', ground = 'black', wait = '2600'] = process.argv.slice(2);
const [W, H] = size.split('x').map(Number);
mkdirSync(out, { recursive: true });
const CH = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const prof = mkdtempSync(join(tmpdir(), 'tw-'));
const port = 9300 + Math.floor(Math.random() * 500);
const p = spawn(CH, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, '--hide-scrollbars', '--no-first-run', `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ver;
for (let i = 0; i < 50; i++) { try { ver = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if (ver.length) break; } catch { } await sleep(150); }
const t = ver.find(x => x.type === 'page');
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map();
ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
  if (d.method === 'Runtime.exceptionThrown') console.log('EXC', d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === 'Runtime.consoleAPICalled' && (d.params.type === 'error' || d.params.type === 'warning')) console.log('CONSOLE', d.params.type, d.params.args.map(a => a.value ?? a.description).join(' '));
  if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error') console.log('LOG', d.params.entry.text, d.params.entry.url || ''); };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: W < 700 });
if (ground === 'paper') await send('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('tower.ground','paper')" });
await send('Page.navigate', { url });
await sleep(+wait);
for (const s of sels.split('|')) {
  const [sel, extra] = s.split('@');
  await send('Runtime.evaluate', { expression: `(()=>{const e=document.getElementById(${JSON.stringify(sel)});if(e)window.scrollTo(0,e.getBoundingClientRect().top+scrollY);${extra ? `(${extra})` : ''}})()` });
  await sleep(+wait);
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(out, `${sel}${extra ? '-' + extra.replace(/\W+/g, '').slice(0, 12) : ''}-${W}-${ground}.png`), Buffer.from(r.result.data, 'base64'));
  console.log('shot', sel);
}
ws.close(); p.kill();
