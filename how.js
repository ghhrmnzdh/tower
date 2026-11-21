/* How it works: one map, six steps.
   Claude Code, Claude Desktop and claude.ai feed one gate; the gate opens
   only while the location check and the path check both pass; Agents hear
   Claude Code's hooks; Usage asks through the gate. Each step lights its
   part of the map and dims the rest. Nothing overlaps: every node has its
   own place, in a wide layout and a narrow one. Requests are small lights
   on the wires; while the gate holds, they wait in line on their own wire
   and go on by themselves when it clears. Runs only while on screen. */
(() => {
'use strict';
const TW = window.TW, root = document.getElementById('howMap');
if (!TW || !root) return;
const $ = (s, r = root) => r.querySelector(s), $$ = (s, r = root) => [...r.querySelectorAll(s)];
const Q = new URLSearchParams(location.search);
const REDUCE = () => matchMedia('(prefers-reduced-motion: reduce)').matches || Q.get('motion') === 'calm';
const STR = Object.assign({ pass: 'Open', geo: 'Holding · off-country', net: 'Holding · no path', through: 'through', waiting: 'waiting' }, (window.TW_T || {}).how);
const NS = 'http://www.w3.org/2000/svg';
const stage = $('.how-stage'), map = $('.how-map'), svg = $('.how-wires'), dots = $('.how-dots');
const steps = $$('.how-steps button'), scen = $$('.how-bar [data-s]'), ro = $('.how-ro'), cap = $('.how-cap');
const N = Object.fromEntries($$('.hn', map).map(e => [e.dataset.n, e]));

/* where everything sits: [x, y, w, h] in design units */
const LAY = {
  wide: { W: 800, H: 460, n: {
    web: [0, 100, 208, 60], desk: [0, 200, 208, 60], code: [0, 300, 208, 60],
    geo: [195, 0, 190, 60], net: [415, 0, 190, 60], gate: [305, 170, 190, 120], api: [600, 200, 200, 60],
    agents: [175, 400, 215, 60], usage: [410, 400, 215, 60] },
    w: { web: ['web', 'r', 'gate', 'l', .5, .3], desk: ['desk', 'r', 'gate', 'l', .5, .5], code: ['code', 'r', 'gate', 'l', .5, .7],
      api: ['gate', 'r', 'api', 'l'], geo: ['geo', 'b', 'gate', 't', .5, .33], net: ['net', 'b', 'gate', 't', .5, .67],
      hooks: ['code', 'b', 'agents', 'l'], usage: ['usage', 't', 'gate', 'b', .5, .67] } },
  narrow: { W: 372, H: 492, n: {
    code: [12, 0, 112, 72], desk: [134, 0, 112, 72], web: [256, 0, 112, 72],
    geo: [12, 148, 96, 72], gate: [125, 124, 130, 120], net: [272, 148, 96, 72], api: [125, 296, 130, 72],
    agents: [12, 420, 172, 72], usage: [196, 420, 172, 72] },
    w: { code: ['code', 'b', 'gate', 't', .5, .25], desk: ['desk', 'b', 'gate', 't', .5, .5], web: ['web', 'b', 'gate', 't', .5, .75],
      api: ['gate', 'b', 'api', 't'], geo: ['geo', 'r', 'gate', 'l'], net: ['net', 'l', 'gate', 'r'],
      hooks: 'M12 36C5 36 4 40 4 47V445C4 452 5 456 12 456', usage: ['usage', 't', 'gate', 'r', .5, .9] } },
};
/* each step lights these nodes and wires */
const STEPS = [
  { n: ['web', 'desk', 'code', 'gate', 'api'], w: ['web', 'desk', 'code', 'api'] },
  { n: ['geo', 'gate'], w: ['geo'] },
  { n: ['net', 'gate', 'api'], w: ['net', 'api'] },
  { n: ['web', 'desk', 'code', 'gate'], w: ['web', 'desk', 'code'], demo: 'geo' },
  { n: ['code', 'agents'], w: ['hooks'] },
  { n: ['usage', 'gate', 'api'], w: ['usage', 'api'] },
];
const NODE_STEP = { web: 0, desk: 0, code: 0, api: 0, gate: 3, geo: 1, net: 2, agents: 4, usage: 5 };

/* the wires */
const W = {};
for (const k of ['web', 'desk', 'code', 'api', 'geo', 'net', 'hooks', 'usage']) {
  const p = document.createElementNS(NS, 'path'); p.dataset.w = k; if (k === 'hooks') p.classList.add('ev'); svg.appendChild(p); W[k] = p;
}
const anchor = ([x, y, w, h], side, f = .5) => side === 'l' ? [x, y + h * f, -1, 0] : side === 'r' ? [x + w, y + h * f, 1, 0] : side === 't' ? [x + w * f, y, 0, -1] : [x + w * f, y + h, 0, 1];
function wire(lay, spec) {
  if (typeof spec === 'string') return spec;
  const [a, sa, b, sb, fa, fb] = spec, [x0, y0, nx0, ny0] = anchor(lay.n[a], sa, fa), [x1, y1, nx1, ny1] = anchor(lay.n[b], sb, fb);
  const d = Math.max(24, Math.hypot(x1 - x0, y1 - y0) * .45);
  return `M${x0} ${y0}C${x0 + nx0 * d} ${y0 + ny0 * d} ${x1 + nx1 * d} ${y1 + ny1 * d} ${x1} ${y1}`;
}
let mode = '', LEN = {};
function layout() {
  const cw = stage.clientWidth; if (!cw) return;
  const m = cw < 620 ? 'narrow' : 'wide', lay = LAY[m];
  const k = Math.min(1.15, cw / lay.W);
  map.style.width = lay.W + 'px'; map.style.height = lay.H + 'px'; map.style.transform = `scale(${k})`;
  map.style.left = ((cw - lay.W * k) / 2).toFixed(1) + 'px';
  stage.style.height = (lay.H * k) + 'px';
  if (m === mode) return;
  mode = m; map.classList.toggle('narrow', m === 'narrow');
  svg.setAttribute('viewBox', `0 0 ${lay.W} ${lay.H}`); dots.setAttribute('viewBox', `0 0 ${lay.W} ${lay.H}`);
  for (const [k2, [x, y, w, h]] of Object.entries(lay.n)) Object.assign(N[k2].style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
  for (const [k2, p] of Object.entries(W)) { p.setAttribute('d', wire(lay, lay.w[k2])); LEN[k2] = p.getTotalLength(); }
  for (const r of S.reqs) r.d = Math.min(r.d, LEN[r.path[r.leg]]);
}

/* state */
const S = { step: 0, scen: 'pass', user: false, auto: !REDUCE(), t: 0, since: 0, reqs: [], spawnR: 0, spawnH: .4, spawnU: 1.2, k: 0, through: 0 };
const held = () => S.scen !== 'pass';
const stopAuto = () => { S.auto = false; root.classList.remove('auto'); };
root.classList.toggle('auto', S.auto);
TW.radar($('.rd', N.gate), () => ({ state: S.scen === 'geo' ? 'holdGeo' : S.scen === 'net' ? 'holdNet' : 'clear' }));
function setScen(s, byUser) {
  if (byUser) S.user = true;
  S.scen = s; map.dataset.s = s; root.dataset.s = s;
  scen.forEach(b => { const on = b.dataset.s === s; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
  TW.wake(); readout();
}
function setStep(i, byUser) {
  if (byUser) stopAuto();
  S.step = i; S.since = S.t;
  steps.forEach((b, j) => { b.classList.toggle('on', j === i); b.setAttribute('aria-selected', j === i); b.style.setProperty('--p', 0); });
  const st = STEPS[i];
  if (cap) cap.innerHTML = $('p', steps[i]).innerHTML;
  map.classList.add('focus');
  for (const [k, e] of Object.entries(N)) e.classList.toggle('on', st.n.includes(k));
  for (const [k, p] of Object.entries(W)) p.classList.toggle('on', st.w.includes(k));
  if (!S.user) setScen(st.demo || 'pass');
  TW.wake();
}
steps.forEach((b, i) => b.addEventListener('click', () => setStep(i, true)));
scen.forEach(b => b.addEventListener('click', () => { stopAuto(); setScen(b.dataset.s, true); }));
for (const [k, e] of Object.entries(N)) e.addEventListener('click', () => setStep(NODE_STEP[k], true));

/* the lights */
const h = i => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const SPEED = 150, GAP = 11;
function spawn(kind) {
  const c = document.createElementNS(NS, 'circle'); c.setAttribute('r', kind === 'hook' ? 2 : 2.6); c.classList.add(kind); dots.appendChild(c);
  let path;
  if (kind === 'req') path = [['code', 'desk', 'web'][Math.floor(h(S.k++) * 3)], 'api'];
  else if (kind === 'hook') path = ['hooks'];
  else path = ['usage', 'api'];
  S.reqs.push({ c, kind, path, leg: 0, d: 0, wait: false, out: 0 });
}
function readout() {
  if (!ro) return;
  const waiting = S.reqs.filter(r => r.wait).length;
  const txt = `${STR[S.scen]} · ${S.through.toLocaleString(document.documentElement.lang === 'fa' ? 'fa-IR' : 'en-US')} ${STR.through} · ${waiting.toLocaleString(document.documentElement.lang === 'fa' ? 'fa-IR' : 'en-US')} ${STR.waiting}`;
  if (ro.textContent !== txt) ro.textContent = txt;
}
function step(dt) {
  S.t += dt;
  /* the list advances by itself until you take over */
  if (S.auto) {
    const p = (S.t - S.since) / 7;
    steps[S.step].style.setProperty('--p', Math.min(1, p).toFixed(3));
    if (p >= 1) setStep((S.step + 1) % STEPS.length);
  }
  if ((S.spawnR -= dt) <= 0) { S.spawnR = .5 + .3 * h(S.k + 50); if (S.reqs.filter(r => r.kind === 'req').length < 26) spawn('req'); }
  if ((S.spawnH -= dt) <= 0) { S.spawnH = .7 + .5 * h(S.k + 90); spawn('hook'); }
  if ((S.spawnU -= dt) <= 0) { S.spawnU = 3.4; if (!held()) spawn('use'); }
  const lane = {};
  for (const r of S.reqs) {
    const w = r.path[r.leg], L = LEN[w];
    if (r.leg === 0 && r.kind !== 'hook' && held()) {
      /* wait in line on its own wire, nose to the gate; once they clear,
         they leave in the order they came, already spaced */
      const idx = lane[w] = (lane[w] ?? -1) + 1, stop = L - 6 - idx * GAP;
      if (r.d >= stop) r.wait = true; else { r.d = Math.min(stop, r.d + SPEED * dt); r.wait = r.d >= stop; }
      continue;
    }
    r.wait = false; r.d += SPEED * dt * (r.kind === 'hook' ? 1.15 : 1);
    if (r.d < L) continue;
    if (r.leg < r.path.length - 1) { r.leg++; r.d -= L; continue; }
    if (!r.done) { r.done = true; if (r.kind === 'req') S.through++; }
    r.out += dt;
  }
  /* draw */
  for (const r of S.reqs) {
    const w = r.path[r.leg], pt = W[w].getPointAtLength(Math.min(r.d, LEN[w]));
    r.c.setAttribute('cx', pt.x.toFixed(1)); r.c.setAttribute('cy', pt.y.toFixed(1));
    r.c.classList.toggle('held', r.wait);
    const fadeIn = Math.min(1, (r.leg ? 1 : r.d / 18)), fadeOut = 1 - Math.min(1, r.out / .25);
    r.c.style.opacity = (fadeIn * fadeOut * (W[w].classList.contains('on') ? 1 : .3)).toFixed(2);
  }
  S.reqs = S.reqs.filter(r => { if (r.out >= .25) { r.c.remove(); return false; } return true; });
  readout();
}

/* wire up */
new ResizeObserver(layout).observe(stage);
layout(); setStep(0); setScen('pass');
let last = null;
TW.ticker(root, P => {
  if (REDUCE()) { last = null; return false; }
  const dt = last == null ? 0 : Math.min(.05, P - last); last = P;
  step(dt);
  return true;
});
/* back on screen after a while: pick up without a burst */
document.addEventListener('visibilitychange', () => { last = null; });
})();
