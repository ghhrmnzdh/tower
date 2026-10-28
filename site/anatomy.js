/* Tower, as a machine: the "How it works" figure. Drawn in the manner of the
   Anatomy skill (github.com/wheresryan22/anatomy, MIT): solid isometric parts
   with four-tone shading, painted back to front, a framed card with a live
   readout, and one model driving every moving part. The geometry and the
   little engine below are this page's own.

   The truth it shows: requests from Claude Code, Claude Desktop and claude.ai
   ride one track to Tower's gate. The boom lifts only while the radar has
   your country confirmed AND the probe has a path to Anthropic; otherwise the
   request waits in the bay (503 + Retry-After) and goes on by itself. Hooks
   light the board, /usage moves the gauge only while the gate is green, and
   every screen reads the one state. */
(() => {
'use strict';
const TW = window.TW, svg = document.getElementById('anatSvg');
if (!TW || !svg) return;
const fig = document.getElementById('anat'), ro = document.getElementById('anatRo'), keys = document.getElementById('anatKeys');
const REDUCE = () => matchMedia('(prefers-reduced-motion: reduce)').matches || new URLSearchParams(location.search).get('motion') === 'calm';
const STR = Object.assign({ pass: 'Passing', geo: 'Held · off-country', net: 'Held · no path', through: 'through', held: 'held' }, (window.TW_T || {}).anat);

/* ── the camera: 32° round, 30° up ── */
const PHI = 32 * Math.PI / 180, EL = 30 * Math.PI / 180;
const cp = Math.cos(PHI), sp = Math.sin(PHI), se = Math.sin(EL), ce = Math.cos(EL);
const VIEW = [ce * sp, ce * cp, se];
const P = (x, y, z = 0) => [x * cp - y * sp, (x * sp + y * cp) * se - z * ce];
const r2 = n => Math.round(n * 100) / 100, r4 = n => Math.round(n * 1e4) / 1e4;
const D = (a, close = true) => 'M' + a.map(p => r2(p[0]) + ' ' + r2(p[1])).join('L') + (close ? 'Z' : '');
const DP = (a, close) => D(a.map(p => P(p[0], p[1], p[2] || 0)), close);
const LX = -.55, LY = .835;
/* the planes: a group drawn in local (u, v) lands on a top or a side face */
const at = (x, y, z) => { const [e, f] = P(x, y, z); return r2(e) + ' ' + r2(f); };
const onTop = (x, y, z) => `matrix(${r4(cp)} ${r4(sp * se)} ${r4(-sp)} ${r4(cp * se)} ${at(x, y, z)})`;
const onFront = (x, y, z) => `matrix(${r4(cp)} ${r4(sp * se)} 0 ${r4(ce)} ${at(x, y, z)})`;   /* plane y = const, u → +x, v → down */
const onRight = (x, y, z) => `matrix(${r4(sp)} ${r4(-cp * se)} 0 ${r4(ce)} ${at(x, y, z)})`;  /* plane x = const, u → −y, v → down */

/* ── the finish: near-black solids, four side tones, a lit outline ── */
const MAT = {
  base: { tp: '#141416', s: ['#0a0a0b', '#0c0c0e', '#0f0f11', '#121214'], ol: '#46474d', cr: '#232428' },
  dark: { tp: '#1b1b1f', s: ['#0d0d0f', '#111113', '#151518', '#19191c'], ol: '#a9aab0', cr: '#34353b' },
  lit: { tp: '#26262b', s: ['#131316', '#18181b', '#1d1d21', '#232327'], ol: '#d9dadf', cr: '#45464d' },
  metal: { tp: '#3b3c42', s: ['#1b1b1f', '#222227', '#2a2b30', '#323338'], ol: '#d2d3d8', cr: '#57585f' },
  white: { tp: '#f4f4f6', s: ['#77787e', '#8d8e94', '#a5a6ac', '#bdbec3'], ol: '#ffffff', cr: '#d4d4d8' },
  amber: { tp: '#f6c96f', s: ['#6f4a12', '#875a17', '#a06d1f', '#bb842a'], ol: '#ffe0a0', cr: '#e6a93c' },
};
const GREEN = '#30d158', AMBER = '#e6a93c', WHITE = '#f2f2f4';
function tone(n) {
  if (n[2] > .6) return 't';
  const h = Math.hypot(n[0], n[1]) || 1, rx = (n[0] * cp - n[1] * sp) / h, ry = (n[0] * sp + n[1] * cp) / h;
  return Math.max(0, Math.min(3, Math.floor((.5 + .5 * (rx * LX + ry * LY)) * 4)));
}
function hull(pts) {
  const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const x = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const q of p) { while (lo.length > 1 && x(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (up.length > 1 && x(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function solid(faces, all, creases, m) {
  const b = [[], [], [], []], top = [];
  for (const f of faces) (f.k === 't' ? top : b[f.k]).push(D(f.q));
  let s = '';
  b.forEach((d, i) => { if (d.length) s += `<path fill="${m.s[i]}" stroke="${m.s[i]}" stroke-width=".5" d="${d.join('')}"/>`; });
  if (top.length) s += `<path fill="${m.tp}" stroke="${m.tp}" stroke-width=".4" d="${top.join('')}"/>`;
  if (creases.length) s += `<path class="cr" stroke="${m.cr}" d="${creases.join('')}"/>`;
  return s + `<path class="ol" stroke="${m.ol}" d="${D(hull(all))}"/>`;
}
/* a convex plan, extruded */
function prism(poly, z0, z1, m) {
  const n = poly.length; let cx = 0, cy = 0;
  for (const p of poly) { cx += p[0]; cy += p[1]; } cx /= n; cy /= n;
  const E = poly.map((a, i) => {
    const b = poly[(i + 1) % n]; let nx = b[1] - a[1], ny = a[0] - b[0]; const L = Math.hypot(nx, ny) || 1; nx /= L; ny /= L;
    if (nx * ((a[0] + b[0]) / 2 - cx) + ny * ((a[1] + b[1]) / 2 - cy) < 0) { nx = -nx; ny = -ny; }
    return { a, b, nx, ny, v: nx * VIEW[0] + ny * VIEW[1] > 1e-6 };
  });
  const faces = [], cr = [], all = [];
  for (const e of E) if (e.v) faces.push({ q: [P(e.a[0], e.a[1], z0), P(e.b[0], e.b[1], z0), P(e.b[0], e.b[1], z1), P(e.a[0], e.a[1], z1)], k: tone([e.nx, e.ny, 0]) });
  faces.push({ q: poly.map(p => P(p[0], p[1], z1)), k: 't' });
  E.forEach((e, i) => {
    const f = E[(i + 1) % n];
    if (e.v) cr.push(D([P(e.a[0], e.a[1], z1), P(e.b[0], e.b[1], z1)], false));
    if (e.v && f.v && e.nx * f.nx + e.ny * f.ny < .9) cr.push(D([P(e.b[0], e.b[1], z0), P(e.b[0], e.b[1], z1)], false));
  });
  for (const p of poly) all.push(P(p[0], p[1], z0), P(p[0], p[1], z1));
  return solid(faces, all, cr, m);
}
/* a box on any axes: the boom */
function obox(c, U, V, W, hu, hv, hw, m) {
  const A = [[U, hu], [V, hv], [W, hw]];
  const pt = co => { const q = [c[0], c[1], c[2]]; for (let k = 0; k < 3; k++) for (let j = 0; j < 3; j++) q[j] += A[k][0][j] * co[k] * A[k][1]; return P(q[0], q[1], q[2]); };
  const faces = [], all = [], cr = [];
  for (let k = 0; k < 3; k++) for (const s of [-1, 1]) {
    const n = A[k][0].map(v => v * s);
    if (n[0] * VIEW[0] + n[1] * VIEW[1] + n[2] * VIEW[2] <= 1e-6) continue;
    const q = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([i, j]) => { const co = [0, 0, 0]; co[k] = s; co[(k + 1) % 3] = i; co[(k + 2) % 3] = j; return pt(co); });
    faces.push({ q, k: tone(n) }); cr.push(D(q));
  }
  for (const a of [-1, 1]) for (const b of [-1, 1]) for (const d of [-1, 1]) all.push(pt([a, b, d]));
  return solid(faces, all, cr, m);
}
const rect = (x, y, w, d) => [[x, y], [x + w, y], [x + w, y + d], [x, y + d]];
const rrect = (x, y, w, d, r, k = 5) => {
  const out = [];
  for (const [cx, cy, a0] of [[x + w - r, y + r, -90], [x + w - r, y + d - r, 0], [x + r, y + d - r, 90], [x + r, y + r, 180]])
    for (let i = 0; i <= k; i++) { const a = (a0 + 90 * i / k) * Math.PI / 180; out.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); }
  return out;
};
const circ = (cx, cy, r, k = 28) => [...Array(k)].map((_, i) => { const a = i / k * 2 * Math.PI; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; });
const box = (x, y, w, d, z0, z1, m) => prism(rect(x, y, w, d), z0, z1, m);
const cyl = (cx, cy, r, z0, z1, m, k) => prism(circ(cx, cy, r, k), z0, z1, m);
/* a ribbon of track between two plan points */
const ribbon = (a, b, w, z0, z1, m) => {
  const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy), nx = -dy / L * w / 2, ny = dx / L * w / 2;
  return prism([[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]], z0, z1, m);
};
const tube = (pts, w, col = '#1b1b1f', ol = '#7d7e84', id = '') => `<path${id ? ` id="${id}o"` : ''} class="tb" stroke="${ol}" stroke-width="${w + 1.6}" d="${DP(pts, false)}"/><path${id ? ` id="${id}"` : ''} class="tb" stroke="${col}" stroke-width="${w}" d="${DP(pts, false)}"/>`;
function path3(pts) {
  const seg = []; let L = 0;
  for (let i = 1; i < pts.length; i++) { const a = pts[i - 1], b = pts[i], l = Math.hypot(b[0] - a[0], b[1] - a[1], (b[2] || 0) - (a[2] || 0)); seg.push([a, b, L, l]); L += l; }
  return { L, at(s) { s = Math.max(0, Math.min(L, s)); for (const [a, b, L0, l] of seg) if (s <= L0 + l + 1e-9) { const k = l ? (s - L0) / l : 0; return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, (a[2] || 0) + ((b[2] || 0) - (a[2] || 0)) * k]; } const z = seg[seg.length - 1][1]; return [z[0], z[1], z[2] || 0]; } };
}
const part = (k, inner, extra = '') => `<g class="part" data-part="${k}"${extra}>${inner}</g>`;
const ell = (x, y, z, r, attrs) => { const [cx, cy] = P(x, y, z); return `<ellipse cx="${r2(cx)}" cy="${r2(cy)}" rx="${r2(r)}" ry="${r2(r * se)}" ${attrs}/>`; };

/* ── the model's fixed places ── */
const MERGE = 262, STOP = 618, END = 1000, GAP = 24, SPEED = 150, TRACK_Z = 7;
const LANES = [
  { k: 'web', pts: [[82, 80], [150, 80], [MERGE, 200]], tint: '#7aa7ff', w: .2 },
  { k: 'desk', pts: [[82, 200], [MERGE, 200]], tint: '#d97757', w: .27 },
  { k: 'code', pts: [[82, 320], [150, 320], [MERGE, 200]], tint: '#f2f2f4', w: .53 },
];
LANES.forEach(l => { l.path = path3(l.pts.map(p => [p[0], p[1], TRACK_Z])); l.L = l.path.L; });
const PIN_IN = [415, 0], PIN_OUT = [507, 74], BEACONS = [[318, -92], [512, -92], [318, 92]];
const PROBE_L = [[630, 288, 26], [648, 288, 26], [664, 322, 3], [692, 322, 3]];
const PROBE_R = [[724, 322, 3], [984, 322, 3], [994, 304, 20]];
const HOOK = [[90, 350, 16], [110, 350, 2], [128, 481, 2], [150, 481, 12]];
const hookPath = path3(HOOK);
const ARM = { pivot: [636, 262, 68], L: 122 };

/* ══════════════════════════ the drawing, back to front ══════════════════════════ */
function build() {
  let s = '';
  s += `<defs>
    <pattern id="anHatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="9" fill="${AMBER}"/></pattern>
    <radialGradient id="anGlowG"><stop offset="0" stop-color="${GREEN}" stop-opacity=".75"/><stop offset="1" stop-color="${GREEN}" stop-opacity="0"/></radialGradient>
    <radialGradient id="anGlowA"><stop offset="0" stop-color="${AMBER}" stop-opacity=".8"/><stop offset="1" stop-color="${AMBER}" stop-opacity="0"/></radialGradient>
    <radialGradient id="anGlowW"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
    <radialGradient id="anPinHead" cx=".38" cy=".34" r=".7"><stop offset="0" stop-color="#fff"/><stop offset=".55" stop-color="#d9dade"/><stop offset="1" stop-color="#7d7e84"/></radialGradient>
    <linearGradient id="anGlass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#16171b"/><stop offset="1" stop-color="#060607"/></linearGradient>
  </defs>`;
  /* the bench: feet, plate, bevel, screws, a ruler along the front, one engraved label */
  s += [[-20, -80], [1060, -80], [-20, 510], [1060, 510]].map(([x, y]) => cyl(x, y, 15, -34, -22, MAT.dark, 20)).join('');
  s += prism(rrect(-70, -130, 1180, 690, 36), -22, 0, MAT.base);
  s += `<path class="ln faint" d="${DP(rrect(-56, -116, 1152, 662, 26).map(p => [p[0], p[1], 0]))}"/>`;
  s += [[-42, -102], [1082, -102], [-42, 532], [1082, 532]].map(([x, y]) => `<g transform="${onTop(x, y, 0)}"><circle r="5" class="screw"/><path d="M-3 -1.2L3 1.2" class="ln mid"/></g>`).join('');
  s += `<g transform="${onFront(0, 560, 0)}">${[...Array(53)].map((_, i) => `<path class="ln ${i % 5 ? 'faint' : 'mid'}" d="M${i * 20} 3V${i % 5 ? 8 : 13}"/>`).join('')}</g>`;
  s += `<g transform="${onFront(838, 560, 0)}"><rect x="0" y="4" width="196" height="14" rx="2" class="plate"/><text x="98" y="13.6" class="eng" text-anchor="middle">TOWER · 127.0.0.1:8888</text></g>`;

  /* 3 · the radar: a fenced paddock, three location sources, the tower */
  let rd = box(300, -110, 230, 220, 0, 6, MAT.dark);
  rd += `<g transform="${onTop(PIN_IN[0], PIN_IN[1], 6)}"><circle r="72" id="anZone" fill="${GREEN}" fill-opacity=".07"/>`
    + [[34, .9], [52, .7], [64, 1.1]].map(([r, w], i) => `<path class="ln faint" d="${blob(r, i)}"/>`).join('')
    + `</g><g transform="${onTop(300, -110, 6)}">${[...Array(9)].flatMap((_, i) => [...Array(9)].map((_, j) => { const x = 13 + i * 25.5, y = 13 + j * 24.3, dx = x - 115, dy = y - 110; return Math.hypot(dx, dy) > 80 ? `<circle cx="${r2(x)}" cy="${r2(y)}" r="1.1" class="dotg"/>` : ''; })).join('')}</g>`;
  const beacon = ([x, y], i) => box(x - 7, y - 7, 14, 14, 6, 11, MAT.metal) + `<path class="mast" d="${DP([[x, y, 11], [x, y, 58]], false)}"/>` + cyl(x, y, 4.5, 58, 63, MAT.metal, 14) + `<g id="anBc${i}">${ell(x, y, 66, 3.2, `fill="${GREEN}"`)}</g>`;
  rd += beacon(BEACONS[0], 0) + beacon(BEACONS[1], 1);
  const ring = (z, front) => { const pts = []; for (let i = 0; i <= 48; i++) { const a = i / 48 * 2 * Math.PI, x = PIN_IN[0] + 72 * Math.cos(a), y = PIN_IN[1] + 72 * Math.sin(a); const d = (x - PIN_IN[0]) * sp + (y - PIN_IN[1]) * cp; if ((d >= 0) === front) pts.push([x, y, z]); else if (pts.length && pts[pts.length - 1] !== null) pts.push(null); } return pts.reduce((acc, p) => { if (p === null) acc.push([]); else acc[acc.length - 1].push(p); return acc; }, [[]]).filter(a => a.length > 1).map(a => DP(a, false)).join(''); };
  const posts = front => [...Array(20)].map((_, i) => { const a = i / 20 * 2 * Math.PI, x = PIN_IN[0] + 72 * Math.cos(a), y = PIN_IN[1] + 72 * Math.sin(a); return { x, y, d: (x - PIN_IN[0]) * sp + (y - PIN_IN[1]) * cp }; }).filter(p => (p.d >= 0) === front).sort((a, b) => a.d - b.d).map(p => cyl(p.x, p.y, 2.4, 6, 27, MAT.metal, 8)).join('');
  rd += `<path class="rail" id="anRailB" d="${ring(15, false)}${ring(23, false)}"/>` + posts(false);
  rd += posts(true) + `<path class="rail" id="anRailF" d="${ring(15, true)}${ring(23, true)}"/>`;
  rd += beacon(BEACONS[2], 2);
  rd += `<g id="anLines">${BEACONS.map(() => '<path class="bl"/>').join('')}</g>`;
  rd += `<g id="anPin"><ellipse class="pring" cx="0" cy="0" rx="14" ry="${r2(14 * se)}"/>${cyl(0, 0, 2.6, 0, 26, MAT.metal, 10).replace(/<path class="ol"[^>]*>/, '')}<circle cx="${r2(P(0, 0, 33)[0])}" cy="${r2(P(0, 0, 33)[1])}" r="8.5" fill="url(#anPinHead)" stroke="#fff" stroke-width=".6" id="anPinHead2"/></g>`;
  s += part('radar', rd);

  /* the tower: four legs, bracing, the cab and the radar on its roof */
  const LB = [[606, -76], [654, -76], [654, -24], [606, -24]], LT = [[614, -68], [646, -68], [646, -32], [614, -32]];
  const leg = i => `<path class="legO" d="${DP([[...LB[i], 0], [...LT[i], 150]], false)}"/><path class="leg" d="${DP([[...LB[i], 0], [...LT[i], 150]], false)}"/>`;
  const lerp2 = (a, b, k) => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
  const brace = (i, j) => { let d = ''; for (let t = 0; t < 3; t++) { const k0 = t / 3, k1 = (t + 1) / 3, a0 = [...lerp2(LB[i], LT[i], k0), k0 * 150], a1 = [...lerp2(LB[i], LT[i], k1), k1 * 150], b0 = [...lerp2(LB[j], LT[j], k0), k0 * 150], b1 = [...lerp2(LB[j], LT[j], k1), k1 * 150]; d += DP([a0, b1], false) + DP([b0, a1], false) + DP([a1, b1], false); } return d; };
  let tw = LB.map(([x, y]) => box(x - 6, y - 6, 12, 12, 0, 4, MAT.metal)).join('');
  tw += leg(0) + leg(1) + leg(3) + `<path class="brace back" d="${brace(0, 1)}${brace(0, 3)}"/>` + `<path class="brace" d="${brace(3, 2)}${brace(1, 2)}"/>` + leg(2);
  tw += box(602, -80, 56, 60, 150, 178, MAT.lit) + box(599, -83, 62, 66, 178, 182, MAT.metal);
  tw += `<g transform="${onFront(602, -20, 178)}"><rect x="5" y="6" width="46" height="13" rx="1.5" fill="url(#anGlass)" stroke="#55565d" stroke-width=".5"/><rect x="5" y="6" width="46" height="13" rx="1.5" id="anWin1" fill="${GREEN}" fill-opacity=".08"/><path class="ln faint" d="M20 6V19M36 6V19"/></g>`;
  tw += `<g transform="${onRight(658, -20, 178)}"><rect x="5" y="6" width="50" height="13" rx="1.5" fill="url(#anGlass)" stroke="#55565d" stroke-width=".5"/><rect x="5" y="6" width="50" height="13" rx="1.5" id="anWin2" fill="${GREEN}" fill-opacity=".06"/><path class="ln faint" d="M22 6V19M39 6V19"/></g>`;
  tw += cyl(630, -50, 36, 182, 187, MAT.metal, 36);
  tw += `<g transform="${onTop(630, -50, 187)}"><circle r="30" fill="#0b0b0d" stroke="#57585f" stroke-width=".6"/><circle r="26" id="anRing" fill="none" stroke="${GREEN}" stroke-width="2.6"/><g id="anSweep"><path d="M0 0L26 0A26 26 0 0 0 ${r2(26 * Math.cos(-.95))} ${r2(26 * Math.sin(-.95))}Z" fill="${GREEN}" fill-opacity=".22" id="anSweepF"/><path d="M0 0L26 0" stroke="${GREEN}" stroke-width="1.6" id="anSweepL"/></g><g id="anBlips"><circle cx="9" cy="-8" r="2" fill="${GREEN}"/><circle cx="-11" cy="5" r="2" fill="${GREEN}"/><circle cx="6" cy="12" r="2" fill="${GREEN}"/></g><circle r="3.4" id="anHub" fill="${GREEN}"/></g>`;
  tw += `<path class="mast" d="${DP([[630, -50, 187], [630, -50, 214]], false)}"/>` + `<circle cx="${r2(P(630, -50, 216)[0])}" cy="${r2(P(630, -50, 216)[1])}" r="2.6" fill="#f2f2f4"/>`;
  s += part('radar', tw);

  /* the radar's cable to the gate, under the track */
  s += part('radar', tube([[630, -22, 2], [630, 150, 2], [612, 246, 2]], 3.6));

  /* 1 · every Claude: three stations, each with its own window */
  const station = (y, kind) => {
    let o = box(-30, y, 120, 80, 0, 70, MAT.lit) + box(-34, y - 4, 128, 88, 70, 75, MAT.metal);
    o += `<g transform="${onFront(-30, y + 80, 70)}"><rect x="7" y="7" width="106" height="50" rx="3" fill="url(#anGlass)" stroke="#5c5d64" stroke-width=".6"/>${screen(kind)}<g class="leds">${[0, 1, 2].map(i => `<circle cx="${12 + i * 7}" cy="63.5" r="1.5" fill="${i ? '#3a3b41' : GREEN}"/>`).join('')}</g><path class="ln faint" d="M60 62H108"/></g>`;
    o += `<g transform="${onRight(90, y + 80, 70)}"><rect x="29" y="50" width="22" height="15" rx="2" fill="#040405" stroke="#55565d" stroke-width=".6"/><circle cx="70" cy="9" r="1.8" fill="${GREEN}"/><path class="ln faint" d="M6 30H22M6 34H22M6 38H22"/></g>`;
    return o;
  };
  s += part('src', station(40, 'web') + station(160, 'desk') + station(280, 'code'));

  /* the track: feeders, the junction, the main line, the bay */
  let tr = '';
  for (const l of [LANES[0], LANES[2]]) { tr += ribbon(l.pts[0], l.pts[1], 40, 0, 6, MAT.dark) + ribbon(l.pts[1], l.pts[2], 40, 0, 6, MAT.dark) + cyl(l.pts[1][0], l.pts[1][1], 20, 0, 6, MAT.dark, 24); }
  tr += ribbon([70, 200], [END, 200], 46, 0, 6, MAT.dark);
  tr += `<path class="tie" d="${[...Array(46)].map((_, i) => { const x = 90 + i * 20; return x > MERGE - 30 && x < MERGE + 30 ? '' : DP([[x, 182, 6], [x, 218, 6]], false); }).join('')}"/>`;
  tr += `<path class="railt" d="${DP([[82, 187, 6], [END, 187, 6]], false)}${DP([[82, 213, 6], [END, 213, 6]], false)}"/>`;
  for (const l of [LANES[0], LANES[2]]) {
    const segs = [[l.pts[0], l.pts[1]], [l.pts[1], l.pts[2]]];
    tr += `<path class="railt" d="${segs.map(([a, b]) => { const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy), nx = -dy / L * 13, ny = dx / L * 13; return DP([[a[0] + nx, a[1] + ny, 6], [b[0] + nx, b[1] + ny, 6]], false) + DP([[a[0] - nx, a[1] - ny, 6], [b[0] - nx, b[1] - ny, 6]], false); }).join('')}"/>`;
  }
  tr += cyl(MERGE, 200, 34, 0, 7, MAT.metal, 36) + `<g transform="${onTop(MERGE, 200, 7)}"><circle r="24" class="ln faint" fill="none"/>${[...Array(8)].map((_, i) => `<circle cx="${r2(29 * Math.cos(i * Math.PI / 4))}" cy="${r2(29 * Math.sin(i * Math.PI / 4))}" r="1.4" class="screw"/>`).join('')}</g>`;
  tr += `<g transform="${onTop(700, 200, 6)}">${[0, 90, 180].map(x => `<path class="chev" d="M${x - 5} -7L${x + 3} 0L${x - 5} 7"/>`).join('')}</g>`;
  s += tr;
  s += part('bay', `<g transform="${onTop(522, 177, 6)}"><rect width="${STOP + 10 - 522}" height="46" fill="url(#anHatch)" id="anBay" opacity=".18"/><path d="M${STOP + 10 - 522} 0V46" stroke="#f2f2f4" stroke-width="2" id="anStop"/></g>`);

  /* 2 · the gate's back post, where the boom rests */
  s += part('gate', cyl(636, 150, 5.5, 0, 62, MAT.metal, 14) + box(629, 143, 14, 14, 62, 66, MAT.metal));
  /* the hook cable, Claude Code → the board */
  s += part('board', tube(HOOK, 3.4) + `<circle id="anHookP" r="3" fill="#fff" opacity="0"/>`);
  /* the requests themselves */
  s += `<g id="anPucks"></g>`;
  /* 2 · the gate: cabinet, lamps, the arm */
  let gt = box(572, 246, 58, 52, 0, 84, MAT.lit) + box(569, 243, 64, 58, 84, 89, MAT.metal);
  gt += `<g transform="${onFront(572, 298, 84)}"><rect x="5" y="6" width="48" height="72" rx="2" class="ln faint" fill="none"/>${[0, 1, 2, 3, 4].map(i => `<path class="ln mid" d="M12 ${58 + i * 3.6}H46"/>`).join('')}<circle cx="47" cy="12" r="2.2" id="anLed" fill="${GREEN}"/>${[[9, 10], [49, 74], [9, 74]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.3" class="screw"/>`).join('')}</g>`;
  gt += `<g transform="${onRight(630, 298, 84)}"><rect x="6" y="8" width="40" height="62" rx="2" class="ln faint" fill="none"/><path class="ln mid" d="M40 34V44"/></g>`;
  gt += cyl(601, 272, 4, 89, 116, MAT.metal, 12) + box(588, 262, 26, 20, 116, 170, MAT.dark) + box(586, 260, 30, 24, 170, 173, MAT.metal);
  gt += `<g transform="${onFront(588, 282, 170)}"><circle cx="13" cy="21" r="10" fill="url(#anGlowG)" id="anGlowGeo"/><circle cx="13" cy="21" r="7" fill="#08080a" stroke="#6a6b71" stroke-width=".7"/><circle cx="13" cy="21" r="5.4" fill="${GREEN}" id="anLensGeo"/><circle cx="13" cy="41" r="10" fill="url(#anGlowG)" id="anGlowNet"/><circle cx="13" cy="41" r="7" fill="#08080a" stroke="#6a6b71" stroke-width=".7"/><circle cx="13" cy="41" r="5.4" fill="${GREEN}" id="anLensNet"/></g>`;
  gt += box(589, 282, 24, 7, 158, 160, MAT.metal) + box(589, 282, 24, 7, 138, 140, MAT.metal);
  gt += `<g transform="${onRight(630, 262, 68)}"><circle r="9" fill="#2a2b30" stroke="#d2d3d8" stroke-width=".6"/><circle r="3.5" fill="#55565d"/></g>`;
  s += part('gate', gt);
  s += part('gate', `<g id="anArm"></g>`);
  /* 4 · the probe: a cable to Anthropic with a coupler that comes apart */
  s += part('probe', tube(PROBE_L, 4.4, '#1b1b1f', '#8d8e94', 'anPL') + tube(PROBE_R, 4.4, '#1b1b1f', '#8d8e94', 'anPR')
    + `<g id="anCplL">${box(692, 315, 14, 14, 0, 12, MAT.metal)}</g><g id="anCplR">${box(710, 315, 14, 14, 0, 12, MAT.metal)}</g><g id="anSpark" opacity="0">${[0, 1, 2, 3].map(i => `<circle r="1.4" fill="${AMBER}"/>`).join('')}</g><circle id="anPulse" r="3.2" fill="#fff"/>`);
  /* the cables to the gauge and the screens */
  s += part('gauge', tube([[592, 298, 8], [592, 338, 2], [520, 420, 2], [520, 458, 6]], 3));
  s += part('screen', tube([[616, 298, 8], [646, 352, 2], [955, 462, 2], [955, 484, 4]], 3));
  /* Anthropic: a rack at the end of the line */
  let rk = box(960, 110, 120, 190, 0, 124, MAT.lit) + box(957, 107, 126, 196, 124, 128, MAT.metal);
  rk += `<g transform="${onFront(960, 300, 124)}">${[...Array(11)].map((_, i) => `<rect x="6" y="${7 + i * 10.4}" width="108" height="8.4" rx="1" fill="#0c0c0e" stroke="#3c3d43" stroke-width=".5"/><path class="ln faint" d="M12 ${11.2 + i * 10.4}H70"/>`).join('')}<g id="anRackLeds">${[...Array(11)].map((_, i) => `<circle cx="100" cy="${11.2 + i * 10.4}" r="1.5" fill="${GREEN}"/><circle cx="106" cy="${11.2 + i * 10.4}" r="1.5" fill="#f2f2f4"/>`).join('')}</g></g>`;
  rk += `<g transform="${onRight(1080, 300, 124)}">${[...Array(16)].map((_, i) => `<path class="ln faint" d="M${18 + i * 10} 20V104"/>`).join('')}</g>`;
  rk += box(988, 300, 12, 5, 13, 27, MAT.metal);
  s += part('probe', rk);

  /* 6 · the board: one lamp per agent, lit by hooks */
  let bd = box(150, 450, 230, 62, 0, 60, MAT.lit) + box(147, 447, 236, 68, 60, 64, MAT.metal);
  bd += `<g transform="${onTop(147, 447, 64)}">${[...Array(7)].map((_, i) => `<rect x="${22 + i * 30.3}" y="20" width="9" height="16" rx="2" fill="#0d0d0f" stroke="#55565d" stroke-width=".5"/><rect x="${23.5 + i * 30.3}" y="${i % 3 ? 22 : 28}" width="6" height="6" rx="1" fill="#bdbec3"/>`).join('')}</g>`;
  bd += `<g transform="${onFront(150, 512, 60)}"><g id="anLamps">${[...Array(14)].map((_, i) => { const u = 23 + (i % 7) * 30.6, v = i < 7 ? 17 : 39; return `<circle cx="${u}" cy="${v}" r="11" class="lg" fill="url(#anGlowW)"/><circle cx="${u}" cy="${v}" r="7.2" fill="#08080a" stroke="#64656b" stroke-width=".7"/><circle cx="${u}" cy="${v}" r="5" class="lz" fill="#f2f2f4"/>`; }).join('')}</g>${[[6, 6], [224, 6], [6, 54], [224, 54]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.3" class="screw"/>`).join('')}</g>`;
  s += part('board', bd);
  /* 7 · the gauge: plan limits, read only while the gate is green */
  let gg = box(470, 456, 100, 56, 0, 10, MAT.metal) + cyl(520, 472, 5, 10, 50, MAT.metal, 12);
  gg += [468, 470.5, 473, 475.5].map((y, i) => `<g transform="${onFront(520, y, 86)}"><circle r="35" fill="${i ? '#1b1b1f' : '#141417'}" ${i ? '' : 'stroke="#8d8e94" stroke-width=".6"'}/></g>`).join('');
  gg += `<g transform="${onFront(520, 478, 86)}"><circle r="35" fill="#0b0b0d" stroke="#d2d3d8" stroke-width=".8"/><circle r="31.5" fill="none" stroke="#2c2d33" stroke-width="2.4"/><g id="anDial">`
    + [...Array(21)].map((_, i) => { const b = (135 + 270 * i / 20) * Math.PI / 180, r0 = i % 5 ? 26.5 : 24.5; return `<path d="M${r2(r0 * Math.cos(b))} ${r2(r0 * Math.sin(b))}L${r2(29 * Math.cos(b))} ${r2(29 * Math.sin(b))}" stroke="${i % 5 ? '#6a6b71' : '#d2d3d8'}" stroke-width="${i % 5 ? .7 : 1.3}"/>`; }).join('')
    + `<path d="${arc(21, 135, 135 + 270 * .47)}" fill="none" stroke="#f2f2f4" stroke-width="2.6" stroke-linecap="round"/><text y="16" class="dig" text-anchor="middle">47%</text><path id="anNeedle" d="M-4 0L25 0" stroke="${AMBER}" stroke-width="1.6" stroke-linecap="round" transform="rotate(${r2(135 + 270 * .47)})"/><circle r="3.4" fill="#d2d3d8"/></g></g>`;
  gg += `<g transform="${onTop(470, 456, 10)}"><circle cx="88" cy="12" r="3.2" fill="#2a2b30" id="anPause"/></g>`;
  s += part('gauge', gg);
  /* 8 · the screens: the menu bar and the dashboard read one state */
  let mn = box(920, 482, 70, 30, 0, 5, MAT.metal) + box(950, 484, 10, 8, 5, 46, MAT.metal) + box(880, 472, 150, 8, 40, 136, MAT.dark);
  mn += `<g transform="${onFront(880, 480, 136)}"><rect x="4" y="4" width="142" height="88" rx="2" fill="#08080a"/><rect x="4" y="4" width="142" height="88" rx="2" fill="url(#anGlass)" opacity=".5"/>
    <rect x="4" y="4" width="142" height="6.5" fill="#fff" fill-opacity=".09"/>${[10, 16, 22, 28].map(x => `<rect x="${x}" y="6.2" width="${x === 10 ? 3 : 4.5}" height="2" rx="1" fill="#fff" fill-opacity=".45"/>`).join('')}<circle cx="114" cy="7.3" r="2.2" fill="none" stroke="#fff" stroke-width=".8" id="anMbR"/><rect x="119" y="6.2" width="7" height="2" rx="1" fill="#fff" fill-opacity=".6"/>
    <rect x="10" y="17" width="74" height="68" rx="3" fill="#161619" stroke="#2f3036" stroke-width=".5"/><rect x="10" y="17" width="18" height="68" rx="3" fill="#1d1d21"/>${[0, 1, 2, 3].map(i => `<rect x="13" y="${28 + i * 7}" width="12" height="2.4" rx="1" fill="#fff" fill-opacity="${i ? .25 : .55}"/>`).join('')}<rect x="32" y="22" width="48" height="13" rx="2" fill="#222226"/><rect x="32" y="38" width="23" height="22" rx="2" fill="#222226"/><rect x="57" y="38" width="23" height="22" rx="2" fill="#222226"/><rect x="32" y="63" width="48" height="18" rx="2" fill="#222226"/>${[0, 1, 2].map(i => `<circle cx="${40 + i * 7}" cy="49" r="2.6" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="1"/>`).join('')}<path d="M35 77L45 71L53 74L63 68L77 70" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width=".7"/>
    <rect x="92" y="13" width="48" height="74" rx="4" fill="#232327" stroke="#3a3b41" stroke-width=".5"/><rect x="95" y="16" width="42" height="13" rx="2.5" fill="#fff" fill-opacity=".05" id="anMonHd"/><circle cx="101" cy="22.5" r="3.4" fill="none" stroke="${GREEN}" stroke-width="1.1" id="anMonR"/><circle cx="101" cy="22.5" r="1" fill="${GREEN}" id="anMonD"/><text x="107" y="24.6" class="mtx" id="anMonT">Protected</text>
    ${[0, 1, 2].map(i => `<circle cx="99" cy="${37 + i * 9}" r="2.2" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width=".8"/><rect x="104" y="${35.6 + i * 9}" width="${[20, 26, 16][i]}" height="1.6" rx=".8" fill="#fff" fill-opacity=".7"/><rect x="104" y="${38.6 + i * 9}" width="${[28, 18, 24][i]}" height="1.2" rx=".6" fill="#fff" fill-opacity=".28"/>`).join('')}
    ${[0, 1, 2].map(i => `<circle cx="${103 + i * 10}" cy="76" r="3.4" fill="none" stroke="#fff" stroke-opacity=".18" stroke-width="1.3"/>`).join('')}</g>`;
  s += part('screen', mn);

  /* the numbered keys, on top of everything */
  const PINS = [['src', [30, 200, 75], 1], ['gate', [606, 298, 24], 2, [14, 74]], ['radar', [630, -50, 218], 3], ['probe', [708, 322, 12], 4, [30, 52]], ['bay', [552, 222, 6], 5, [-34, 92]], ['board', [265, 481, 64], 6], ['gauge', [520, 478, 122], 7], ['screen', [955, 476, 138], 8]];
  s += `<g id="anPins">${PINS.map(([k, p, n, o = [0, -35]]) => { const [x, y] = P(...p), L = Math.hypot(o[0], o[1]), ux = o[0] / L, uy = o[1] / L; return `<g class="pin" data-part="${k}" transform="translate(${r2(x)} ${r2(y)})"><circle r="2.2" class="pd"/><path d="M${r2(ux * 3)} ${r2(uy * 3)}L${r2(o[0] - ux * 11)} ${r2(o[1] - uy * 11)}" class="pl"/><g transform="translate(${o[0]} ${o[1]})"><circle r="10.5" class="pb"/><text y="3.9" text-anchor="middle" class="pn">${n}</text></g></g>`; }).join('')}</g>`;
  return s;
}
function blob(r, seed) {
  const pts = [...Array(36)].map((_, i) => { const a = i / 36 * 2 * Math.PI, k = 1 + .09 * Math.sin(a * 3 + seed * 1.7) + .05 * Math.sin(a * 5 + seed); return [r * k * Math.cos(a), r * k * Math.sin(a) * .9]; });
  return 'M' + pts.map(p => r2(p[0]) + ' ' + r2(p[1])).join('L') + 'Z';
}
function arc(r, a0, a1) {
  const p = a => [r2(r * Math.cos(a * Math.PI / 180)), r2(r * Math.sin(a * Math.PI / 180))];
  return `M${p(a0).join(' ')}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${p(a1).join(' ')}`;
}
function screen(kind) {
  if (kind === 'web') return `<circle cx="13" cy="12" r="1.3" fill="#ff5f57"/><circle cx="17.5" cy="12" r="1.3" fill="#febc2e"/><circle cx="22" cy="12" r="1.3" fill="#28c840"/><rect x="30" y="9.6" width="70" height="5.6" rx="2.8" fill="#1f1f23"/><text x="65" y="13.9" class="stx" text-anchor="middle">claude.ai</text><g transform="translate(60 33) scale(.62) translate(-12 -12)"><path d="${CLAUDE}" fill="#d97757"/></g><rect x="28" y="44" width="64" height="6" rx="3" fill="#1f1f23" stroke="#3a3b41" stroke-width=".4"/>`;
  if (kind === 'desk') return `<circle cx="13" cy="12" r="1.3" fill="#ff5f57"/><circle cx="17.5" cy="12" r="1.3" fill="#febc2e"/><circle cx="22" cy="12" r="1.3" fill="#28c840"/><rect x="8" y="16" width="24" height="40" fill="#141417"/>${[0, 1, 2, 3].map(i => `<rect x="11" y="${22 + i * 6}" width="${[16, 12, 14, 10][i]}" height="1.8" rx=".9" fill="#fff" fill-opacity=".3"/>`).join('')}<g transform="translate(70 26) scale(.46) translate(-12 -12)"><path d="${CLAUDE}" fill="#d97757"/></g><rect x="56" y="36" width="44" height="4" rx="2" fill="#fff" fill-opacity=".14"/><rect x="40" y="44" width="66" height="7" rx="3.5" fill="#1f1f23" stroke="#3a3b41" stroke-width=".4"/>`;
  return `<text x="13" y="18" class="stx t">$ claude</text><text x="13" y="27" class="stx d">● Running tests</text><text x="13" y="35" class="stx d">  ⎿ 148 tools · 21m</text><rect x="13" y="42" width="5" height="7" fill="#f2f2f4" class="cur"/>`;
}
const CLAUDE = 'M12 2.6l1.55 6.05 5.2-3.55-3.55 5.2 6.05 1.55-6.05 1.55 3.55 5.2-5.2-3.55L12 21.4l-1.55-6.05-5.2 3.55 3.55-5.2L2.75 12.15l6.05-1.55-3.55-5.2 5.2 3.55z';

svg.innerHTML = build();
const $ = id => document.getElementById(id);
/* fit the drawing to its card, with room for the card's own labels */
{
  const b = svg.getBBox(), padX = 28, padT = 64, padB = 58;
  const vb = [b.x - padX, b.y - padT, b.width + padX * 2, b.height + padT + padB];
  svg.setAttribute('viewBox', vb.map(r2).join(' '));
  svg.parentElement.style.aspectRatio = `${r2(vb[2])} / ${r2(vb[3])}`;
}

/* ══════════════════════════ the model ══════════════════════════ */
const S = { mode: 'pass', manualAt: -1e9, boom: 1, pin: 0, gap: 0, geoT: 0, netT: 0, sweep: 0, through: 0, held: 0, spawnIn: 0, token: null, hook: null, nextHook: 1.2, last: null, t: 0 };
const lamps = ['work', 'work', 'ny', 'work', 'done', 'work', 'rest', 'work', 'work', 'done', 'work', 'rest', 'work', 'work'];
const pucks = [], layer = $('anPucks');
const PK = { w: cyl(0, 0, 9, TRACK_Z, TRACK_Z + 8, MAT.white, 22), a: cyl(0, 0, 9, TRACK_Z, TRACK_Z + 8, MAT.amber, 22) };
function spawn(lane, s = 0, X = null) {
  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  const [tx, ty] = P(0, 0, TRACK_Z + 8);
  g.innerHTML = ell(0, 0, TRACK_Z, 15, 'class="pr" fill="none"') + PK.w + `<g class="pa" opacity="0">${PK.a}</g><ellipse cx="${r2(tx)}" cy="${r2(ty)}" rx="3" ry="1.5" fill="${lane.tint}"/>`;
  layer.appendChild(g);
  const p = { lane, s, X, g, pa: g.querySelector('.pa'), pr: g.querySelector('.pr'), amb: 0, wait: false };
  pucks.push(p); return p;
}
const posOf = p => p.X != null ? [p.X, 200] : p.lane.path.at(p.s);
function tourMode(t) { const u = t % 24; return u < 8 ? 'pass' : u < 13 ? 'geo' : u < 16 ? 'pass' : u < 21 ? 'net' : 'pass'; }
const follow = (v, to, rate, dt) => v + (to - v) * (1 - Math.exp(-rate * dt));
const mix = (a, b, k) => { const h = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)); const A = h(a), B = h(b); return '#' + A.map((v, i) => Math.round(v + (B[i] - v) * k).toString(16).padStart(2, '0')).join(''); };

function sim(dt, t) {
  const open = S.boom > .72;
  /* the shared line, front to back: nobody passes a closed boom */
  const sh = pucks.filter(p => p.X != null).sort((a, b) => b.X - a.X);
  let ahead = Infinity;
  for (const p of sh) {
    let lim = ahead - GAP; if (!open && p.X <= STOP + .5) lim = Math.min(lim, STOP);
    const nx = Math.min(p.X + SPEED * dt, lim);
    p.wait = nx - p.X < SPEED * dt * .5; p.X = Math.max(p.X, nx); ahead = p.X;
  }
  const tail = sh.length ? sh[sh.length - 1].X : Infinity;
  if (S.token && S.token.X != null && S.token.X >= MERGE + GAP) S.token = null;
  /* the lanes, each to the junction; one at a time through it */
  for (const ln of LANES) {
    const lp = pucks.filter(p => p.lane === ln && p.X == null).sort((a, b) => b.s - a.s);
    let aheadS = Infinity;
    for (const p of lp) {
      let lim = Math.min(aheadS - GAP, ln.L - GAP);
      if (aheadS === Infinity && p.s >= ln.L - GAP - SPEED * dt - .01) {
        if (!S.token && tail >= MERGE + 2 * GAP) S.token = p;
        if (S.token === p) lim = ln.L;
      }
      if (S.token === p && aheadS === Infinity) lim = ln.L;
      const ns = Math.min(p.s + SPEED * dt, lim);
      p.wait = ns - p.s < SPEED * dt * .5; p.s = Math.max(p.s, ns); aheadS = p.s;
      if (S.token === p && p.s >= ln.L - 1e-6) { p.X = MERGE; }
    }
  }
  /* new requests, from whoever is busiest */
  S.spawnIn -= dt;
  if (S.spawnIn <= 0 && pucks.length < 30) {
    S.spawnIn = .38 + Math.random() * .4;
    let r = Math.random(), ln = LANES[2]; for (const l of LANES) { if (r < l.w) { ln = l; break; } r -= l.w; }
    const last = pucks.filter(p => p.lane === ln && p.X == null).reduce((m, p) => Math.min(m, p.s), Infinity);
    if (last > GAP + 2) spawn(ln);
  }
  /* into Anthropic */
  for (let i = pucks.length - 1; i >= 0; i--) if (pucks[i].X != null && pucks[i].X >= END) { pucks[i].g.remove(); if (S.token === pucks[i]) S.token = null; pucks.splice(i, 1); S.through++; }
  S.held = pucks.filter(p => p.wait && !open).length;
}
function paintPucks(t) {
  const open = S.boom > .72;
  for (const p of pucks) {
    let [x, y] = posOf(p);
    const front = p.X != null && !open && p.X >= STOP - .5;
    if (front) { const ph = (t % 1.6) / 1.6; if (ph < .22) x -= 6 * Math.sin(ph / .22 * Math.PI); }   /* 503: back off, retry */
    p.amb = follow(p.amb, p.wait && !open ? 1 : 0, 6, S.dt);
    const [sx, sy] = P(x, y, 0); p.d = x * sp + y * cp;
    p.g.setAttribute('transform', `translate(${r2(sx)} ${r2(sy)})`);
    p.pa.setAttribute('opacity', p.amb.toFixed(2));
    p.pr.setAttribute('stroke', AMBER); p.pr.setAttribute('opacity', (p.amb * (.35 + .35 * Math.sin(t * 5 + x * .05))).toFixed(2));
    p.g.style.opacity = p.X == null ? Math.min(1, p.s / 14).toFixed(2) : p.X > END - 26 ? ((END - p.X) / 26).toFixed(2) : '';
  }
  const order = pucks.slice().sort((a, b) => a.d - b.d);
  if (order.some((p, i) => layer.children[i] !== p.g)) order.forEach(p => layer.appendChild(p.g));
}
function paint(t) {
  const hold = Math.max(S.geoT, S.netT), state = S.mode;
  /* the arm */
  const th = S.boom * 82 * Math.PI / 180, U = [0, -Math.cos(th), Math.sin(th)], W = [0, Math.sin(th), Math.cos(th)];
  const pv = ARM.pivot, L = ARM.L, c = [pv[0], pv[1] + U[1] * (L - 14) / 2, pv[2] + U[2] * (L - 14) / 2];
  const tip = s => [pv[0], pv[1] + U[1] * s + W[1] * 4.1, pv[2] + U[2] * s + W[2] * 4.1];
  const cw = [pv[0], pv[1] - U[1] * 9, pv[2] - U[2] * 9];
  $('anArm').innerHTML = obox(cw, U, [1, 0, 0], W, 7, 6.5, 7, MAT.metal) + obox(c, U, [1, 0, 0], W, (L + 14) / 2, 3.4, 4, MAT.white)
    + `<path d="${DP([tip(12), tip(L - 3)], false)}" stroke="${mix('#c9cace', AMBER, Math.max(hold, 1 - S.boom))}" stroke-width="5" stroke-dasharray="9 9" opacity="${(.35 + .65 * (1 - S.boom)).toFixed(2)}"/>`;
  /* the lamps: one per condition */
  const lamp = (id, k) => { $('anLens' + id).setAttribute('fill', mix(GREEN, AMBER, k)); const g = $('anGlow' + id); g.setAttribute('fill', k > .5 ? 'url(#anGlowA)' : 'url(#anGlowG)'); g.setAttribute('opacity', (k > .5 ? .55 + .45 * Math.sin(t * 5) : .9).toFixed(2)); };
  lamp('Geo', S.geoT); lamp('Net', S.netT);
  $('anLed').setAttribute('fill', mix(GREEN, AMBER, hold));
  $('anBay').setAttribute('opacity', (.14 + .5 * hold * (.75 + .25 * Math.sin(t * 4))).toFixed(2));
  $('anStop').setAttribute('stroke', mix('#f2f2f4', AMBER, hold));
  /* the radar */
  const rc = mix(GREEN, AMBER, hold);
  ['anRing', 'anSweepL'].forEach(i => $(i).setAttribute('stroke', rc)); ['anSweepF', 'anHub'].forEach(i => $(i).setAttribute('fill', rc));
  $('anRing').setAttribute('stroke-dasharray', S.netT > .5 ? '7 6' : '');
  $('anSweep').setAttribute('transform', `rotate(${r2(S.sweep)})`);
  [...$('anBlips').children].forEach((b, i) => { b.setAttribute('fill', rc); b.setAttribute('opacity', (S.geoT > .5 ? .15 : .35 + .6 * Math.max(0, Math.sin(t * 1.6 + i * 2.1))).toFixed(2)); });
  $('anWin1').setAttribute('fill', rc); $('anWin2').setAttribute('fill', rc);
  $('anZone').setAttribute('fill', mix(GREEN, AMBER, S.geoT));
  /* you, inside the fence or not; three sources agree either way */
  const px = PIN_IN[0] + (PIN_OUT[0] - PIN_IN[0]) * S.pin, py = PIN_IN[1] + (PIN_OUT[1] - PIN_IN[1]) * S.pin, [qx, qy] = P(px, py, 6);
  $('anPin').setAttribute('transform', `translate(${r2(qx)} ${r2(qy)})`);
  const pr = $('anPin').querySelector('.pring'); pr.setAttribute('stroke', mix(GREEN, AMBER, S.geoT)); pr.setAttribute('opacity', (.35 + .3 * Math.sin(t * 3)).toFixed(2));
  [...$('anLines').children].forEach((l, i) => { const b = BEACONS[i]; l.setAttribute('d', DP([[b[0], b[1], 66], [px, py, 39]], false)); l.setAttribute('stroke', mix('#bfc0c6', AMBER, S.geoT)); l.setAttribute('stroke-dashoffset', r2(-t * 14)); });
  BEACONS.forEach((_, i) => $('anBc' + i).firstElementChild.setAttribute('fill', mix(GREEN, AMBER, S.geoT)));
  /* the probe: a round trip, or a break on your side */
  const g = S.gap * 7;
  $('anCplL').setAttribute('transform', `translate(${r2(-g * cp)} ${r2(-g * sp * se)})`); $('anCplR').setAttribute('transform', `translate(${r2(g * cp)} ${r2(g * sp * se)})`);
  const PLs = PROBE_L.map((p, i) => i === PROBE_L.length - 1 ? [p[0] - g, p[1], p[2]] : p), PRs = PROBE_R.map((p, i) => i === 0 ? [p[0] + g, p[1], p[2]] : p);
  $('anPL').setAttribute('d', DP(PLs, false)); $('anPLo').setAttribute('d', DP(PLs, false)); $('anPR').setAttribute('d', DP(PRs, false)); $('anPRo').setAttribute('d', DP(PRs, false));
  const pp = path3([...PROBE_L, ...PROBE_R]), cut = path3(PROBE_L).L + 9, per = 1.8, ph = (t % per) / per;
  let ps = pp.L * (ph < .5 ? ph * 2 : 2 - ph * 2), broken = S.gap > .3;
  if (broken) ps = Math.min(ps, cut - 10);
  const [ux, uy] = P(...pp.at(ps)); const pu = $('anPulse'); pu.setAttribute('cx', r2(ux)); pu.setAttribute('cy', r2(uy)); pu.setAttribute('fill', broken ? AMBER : '#fff');
  const spk = $('anSpark'); spk.setAttribute('opacity', broken ? (.5 + .5 * Math.sin(t * 13)).toFixed(2) : '0');
  if (broken) [...spk.children].forEach((c, i) => { const [sx, sy] = P(708 + Math.sin(t * 9 + i * 2) * 4, 322 + Math.cos(t * 7 + i) * 4, 8 + Math.sin(t * 11 + i * 3) * 4); c.setAttribute('cx', r2(sx)); c.setAttribute('cy', r2(sy)); });
  [...$('anRackLeds').children].forEach((c, i) => { if (Math.random() < .06) c.setAttribute('opacity', (.3 + Math.random() * .7).toFixed(2)); });
  /* the board: hooks arrive, a lamp changes */
  if (S.hook) {
    const k = (t - S.hook.t0) / .6;
    if (k >= 1) { lamps[S.hook.i] = S.hook.to; S.hook = null; $('anHookP').setAttribute('opacity', '0'); }
    else { const [hx, hy] = P(...hookPath.at(hookPath.L * k)); const h = $('anHookP'); h.setAttribute('cx', r2(hx)); h.setAttribute('cy', r2(hy)); h.setAttribute('opacity', '1'); }
  }
  const lz = $('anLamps').querySelectorAll('.lz'), lg = $('anLamps').querySelectorAll('.lg');
  lamps.forEach((st, i) => {
    const col = st === 'ny' ? AMBER : st === 'done' ? GREEN : st === 'rest' ? '#2a2b30' : '#f2f2f4';
    const op = st === 'work' ? .62 + .38 * Math.sin(t * 2.2 + i * 1.3) : st === 'ny' ? .45 + .55 * Math.max(0, Math.sin(t * 4.4 + i)) : 1;
    lz[i].setAttribute('fill', col); lz[i].setAttribute('opacity', op.toFixed(2));
    lg[i].setAttribute('fill', st === 'ny' ? 'url(#anGlowA)' : st === 'done' ? 'url(#anGlowG)' : 'url(#anGlowW)'); lg[i].setAttribute('opacity', st === 'rest' ? '0' : (op * .8).toFixed(2));
  });
  /* the gauge rests while the gate does */
  $('anDial').setAttribute('opacity', (1 - .62 * hold).toFixed(2)); $('anPause').setAttribute('fill', mix('#2a2b30', AMBER, hold));
  /* the screens */
  $('anMonT').textContent = hold > .5 ? 'Held' : 'Protected';
  ['anMonR', 'anMbR'].forEach(i => $(i).setAttribute('stroke', i === 'anMbR' ? mix('#ffffff', AMBER, hold) : rc)); $('anMonD').setAttribute('fill', rc);
  $('anMonHd').setAttribute('fill', hold > .5 ? AMBER : '#fff'); $('anMonHd').setAttribute('fill-opacity', hold > .5 ? '.14' : '.05');
}
let roAt = 0;
function readout(t) {
  if (t - roAt < .25 && t > roAt) return; roAt = t;
  const head = S.mode === 'pass' ? STR.pass : STR[S.mode];
  ro.textContent = `${head} · ${S.through.toLocaleString(document.documentElement.lang === 'fa' ? 'fa-IR' : 'en-US')} ${STR.through} · ${S.held.toLocaleString(document.documentElement.lang === 'fa' ? 'fa-IR' : 'en-US')} ${STR.held}`;
  fig.dataset.mode = S.mode;
}
function step(dt, t) {
  S.dt = dt; S.t = t;
  if (t - S.manualAt > 10 && !REDUCE()) S.mode = tourMode(t - S.tourAt);
  const geo = S.mode === 'geo', net = S.mode === 'net';
  S.boom = follow(S.boom, geo || net ? 0 : 1, 3.6, dt);
  S.pin = follow(S.pin, geo ? 1 : 0, 2.4, dt); S.gap = follow(S.gap, net ? 1 : 0, 5, dt);
  S.geoT = follow(S.geoT, geo ? 1 : 0, 4, dt); S.netT = follow(S.netT, net ? 1 : 0, 4, dt);
  S.sweep = (S.sweep + dt * (geo || net ? 70 : 140)) % 360;
  if (!S.hook && t > S.nextHook) {
    S.nextHook = t + 1.8 + Math.random() * 1.6;
    const i = Math.floor(Math.random() * lamps.length), st = lamps[i], ny = lamps.filter(x => x === 'ny').length;
    const to = st === 'work' ? (Math.random() < .35 && ny < 2 ? 'ny' : 'done') : st === 'ny' ? 'work' : st === 'done' ? (Math.random() < .5 ? 'rest' : 'work') : 'work';
    S.hook = { i, to, t0: t };
  }
  sim(dt, t); paintPucks(t); paint(t); readout(t);
}

/* the still: a calm moment, for Reduce Motion */
function still() {
  pucks.splice(0).forEach(p => p.g.remove()); S.token = null;
  [[LANES[0], 30], [LANES[2], 60], [LANES[1], 120]].forEach(([l, s]) => spawn(l, s));
  [330, 420, 520, 760, 880].forEach(X => spawn(LANES[1], LANES[1].L, X));
  const geo = S.mode === 'geo', net = S.mode === 'net';
  S.boom = geo || net ? 0 : 1; S.pin = geo ? 1 : 0; S.gap = net ? 1 : 0; S.geoT = +geo; S.netT = +net; S.dt = 1;
  if (geo || net) { const sh = pucks.filter(p => p.X != null && p.X < STOP).sort((a, b) => b.X - a.X); sh.forEach((p, i) => { p.X = STOP - i * GAP; p.wait = true; }); }
  S.held = pucks.filter(p => p.wait).length;
  pucks.forEach(p => p.amb = p.wait ? 1 : 0);
  paintPucks(0); paint(0); roAt = -1; readout(0);
}

/* the warm-up: a line already moving when it scrolls into view */
S.tourAt = 0; S.clock = 0;
if (REDUCE()) still();
else for (let i = 0; i < 360; i++) step(1 / 60, i / 60);
S.clock = 6;
let last = null;
TW.ticker(svg, Pt => {
  if (REDUCE()) { last = null; return false; }
  if (last == null) last = Pt;
  const dt = Math.min(.05, Math.max(0, Pt - last)); last = Pt; S.clock += dt;
  step(dt, S.clock);
  return true;
});

/* ── touching it ── */
function setMode(m) {
  S.mode = S.mode === m ? 'pass' : m; S.manualAt = S.clock; S.tourAt = S.clock + 10;
  if (REDUCE()) still(); TW.wake();
}
let hotKey = null;
function hot(k) {
  if (k === hotKey) return; hotKey = k;
  fig.classList.toggle('focus', !!k);
  svg.querySelectorAll('.part, .pin').forEach(e => e.classList.toggle('hot', e.dataset.part === k));
  keys?.querySelectorAll('button').forEach(b => b.classList.toggle('hot', b.dataset.part === k));
}
svg.addEventListener('pointerover', e => { const g = e.target.closest('[data-part]'); hot(g ? g.dataset.part : null); });
svg.addEventListener('pointerleave', () => hot(null));
svg.addEventListener('click', e => { const g = e.target.closest('[data-part]'); if (!g) return; if (g.dataset.part === 'radar') setMode('geo'); else if (g.dataset.part === 'probe') setMode('net'); });
keys?.querySelectorAll('button').forEach(b => {
  b.addEventListener('pointerenter', () => hot(b.dataset.part)); b.addEventListener('pointerleave', () => hot(null));
  b.addEventListener('focus', () => hot(b.dataset.part)); b.addEventListener('blur', () => hot(null));
  b.addEventListener('click', () => { if (b.dataset.part === 'radar') setMode('geo'); else if (b.dataset.part === 'probe') setMode('net'); });
});
let inView = false;
new IntersectionObserver(es => { inView = es[0].isIntersecting; }, { threshold: .3 }).observe(svg);
addEventListener('keydown', e => {
  if (!inView || e.metaKey || e.ctrlKey || e.altKey || /input|textarea|select/i.test(document.activeElement?.tagName || '')) return;
  const k = e.key.toLowerCase();
  if (k === 'g') setMode('geo'); else if (k === 'n') setMode('net');
});
/* on a phone, open on the gate */
const stage = svg.parentElement;
const center = () => { if (stage.scrollWidth > stage.clientWidth) stage.scrollLeft = (stage.scrollWidth - stage.clientWidth) * .52; };
center(); addEventListener('resize', center);
})();
