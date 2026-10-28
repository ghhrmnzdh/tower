/* Tower: the site's one script, shared by index.html, fa/index.html and
   og.html. Everything the app draws is ported, not pictured: the radar, the
   model marks and the lamp are src/Glyph.swift line for line on a canvas; the
   popover, menu bar, dashboard and menus are measured from src/Popover.swift,
   src/Dashboard.swift and src/DesignSystem.swift. They stay English and LTR in
   both editions, as the app does. Page copy lives in the HTML; this file only
   brings it to life.

   The hero and the social video share one director: every moving part is a
   pure function of time (springs, not CSS transitions), so the page plays it
   live and og.html renders any instant exactly. */
(() => {
'use strict';
const TW = window.TW = {};
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const RM = matchMedia('(prefers-reduced-motion: reduce)');
const Q = new URLSearchParams(location.search);
let REDUCE = RM.matches || Q.get('motion') === 'calm';
RM.addEventListener?.('change', e => { REDUCE = e.matches; });
const OG = !!window.TW_OG;
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a, b, k) => a + (b - a) * k;
const setText = (e, t) => { if (e && e.textContent !== t) e.textContent = t; };
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const fmt = n => n.toLocaleString('en-US');
TW.$ = $; TW.$$ = $$;

/* ── motion: SwiftUI's springs as functions of time (DesignSystem.Motion) ── */
function spring(t, resp = .45, damp = .85) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI / resp, z = Math.min(damp, .999), wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + z * w / wd * Math.sin(wd * t));
}
const eo = (t, d) => t <= 0 ? 0 : t >= d ? 1 : 1 - Math.pow(1 - t / d, 3);
const win = (u, a, b, r = .45, d = .85) => (u < a ? 0 : spring(u - a, r, d)) * (u < b ? 1 : 1 - spring(u - b, r, d));
TW.spring = spring; TW.eo = eo; TW.win = win; TW.clamp = clamp;

/* ── time ── */
const T0 = Date.now() / 1000;
const now = () => Date.now() / 1000;
function elapsed(s) {
  s = Math.max(0, Math.floor(s));
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + String(s % 60).padStart(2, '0') + 's';
  return Math.floor(s / 3600) + 'h ' + String(Math.floor(s / 60) % 60).padStart(2, '0') + 'm';
}
/* Model.swift agoString, unit for unit */
function ago(s) { s = Math.max(0, s); if (s < 90) return Math.floor(s) + 's'; if (s < 5400) return Math.floor(s / 60) + 'm'; if (s < 129600) return (s / 3600).toFixed(1) + 'h'; return Math.floor(s / 86400) + 'd'; }

/* ══════════════════════════ the symbols ══════════════════════════
   SF Symbols, redrawn on a 24 box. One sprite, injected once. */
const L = (d, w = 1.8) => `<g fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${d}</g>`;
const F = d => `<g fill="currentColor">${d}</g>`;
const SF = {
  globe: L('<circle cx="12" cy="12" r="8.6"/><ellipse cx="12" cy="12" rx="3.8" ry="8.6"/><path d="M3.6 12h16.8M4.9 7.6h14.2M4.9 16.4h14.2"/>', 1.5),
  rack: L('<rect x="3.5" y="4.6" width="17" height="6.4" rx="1.8"/><rect x="3.5" y="13" width="17" height="6.4" rx="1.8"/><path d="M7 7.8h5M7 16.2h5"/>', 1.5) + F('<circle cx="16.6" cy="7.8" r=".95"/><circle cx="16.6" cy="16.2" r=".95"/>'),
  warn: '<path d="M10.3 3.8a2 2 0 0 1 3.4 0l8 13.8A2 2 0 0 1 20 20.6H4a2 2 0 0 1-1.7-3z" fill="currentColor"/><path d="M12 9.2v4.4" stroke="#1d1d1f" stroke-width="2.3" stroke-linecap="round"/><circle cx="12" cy="17" r="1.25" fill="#1d1d1f"/>',
  warnline: L('<path d="M10.3 4.3a2 2 0 0 1 3.4 0l7.6 13.2A2 2 0 0 1 19.6 20.5H4.4a2 2 0 0 1-1.7-3z"/><path d="M12 9.5v4"/>') + F('<circle cx="12" cy="16.8" r="1.1"/>'),
  chev: L('<path d="M9 5.5l6.5 6.5L9 18.5"/>', 2.6),
  chevd: L('<path d="M6 9.5l6 6 6-6"/>', 2.4),
  updown: L('<path d="M8 9.5l4-4 4 4M8 14.5l4 4 4-4"/>', 2.2),
  refresh: L('<path d="M19.2 12.5a7.2 7.2 0 1 1-2.2-5.6"/><path d="M19.5 4.5v4.4h-4.4"/>', 2.2),
  checkf: '<circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M7.4 12.4l3.1 3.1 6.1-6.7" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
  exf: '<circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M12 6.8v6" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/><circle cx="12" cy="16.9" r="1.45" fill="#fff"/>',
  check: L('<path d="M5 12.5l4.5 4.5L19 7.5"/>', 2.2),
  checkc: L('<circle cx="12" cy="12" r="9"/><path d="M7.8 12.3l3 3 5.4-6"/>', 1.8),
  moonzzz: L('<path d="M13.2 6.2a7 7 0 1 0 5.6 10.6 6.2 6.2 0 0 1-5.6-10.6z"/><path d="M15.5 3h3.2l-3.2 3.6h3.2M19.6 8.2h2.2l-2.2 2.4h2.2"/>', 1.6),
  laptop: L('<rect x="4.5" y="5" width="15" height="10.6" rx="1.6"/><path d="M2 18.6h20"/>', 1.6),
  laptopdown: L('<rect x="4.5" y="4.6" width="15" height="11" rx="1.6"/><path d="M12 7v5.6M9.6 10.4 12 12.8l2.4-2.4M2 18.6h20"/>', 1.6),
  macwin: L('<rect x="3" y="4.5" width="18" height="15" rx="3.2"/><path d="M3 9.2h18"/>', 1.6) + F('<circle cx="6" cy="6.9" r=".8"/><circle cx="8.6" cy="6.9" r=".8"/>'),
  macwins: L('<rect x="2.8" y="3.6" width="14.6" height="12" rx="2.6"/><rect x="6.6" y="8.4" width="14.6" height="12" rx="2.6" fill="#2b2b2e"/><path d="M6.6 12.2h14.6"/>', 1.5),
  gear: L('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>', 1.5),
  term: L('<rect x="3" y="4.5" width="18" height="15" rx="3.2"/><path d="M7 9.5l3 2.5-3 2.5M12.5 15H17"/>', 1.6),
  power: L('<path d="M12 3.6v7.6"/><path d="M7.3 6.4a7.4 7.4 0 1 0 9.4 0"/>', 1.9),
  hand: F('<path d="M8.4 11.4V5.6a1.45 1.45 0 0 1 2.9 0v4.9h.4V3.9a1.45 1.45 0 0 1 2.9 0v6.6h.4V5.2a1.45 1.45 0 0 1 2.9 0v6.9h.4V8.4a1.45 1.45 0 0 1 2.9 0v6.2c0 4.3-3 7.6-7.4 7.6h-.6c-2.3 0-4-1-5.4-2.9l-3.3-4.6a1.55 1.55 0 0 1 2.4-1.9z"/>'),
  qbubble: '<path d="M4.5 3.5h15a2.5 2.5 0 0 1 2.5 2.5v9a2.5 2.5 0 0 1-2.5 2.5H11l-4.6 3.6c-.5.4-1.2 0-1.2-.6v-3H4.5A2.5 2.5 0 0 1 2 15V6a2.5 2.5 0 0 1 2.5-2.5z" fill="currentColor"/><path d="M9.7 8.4a2.3 2.3 0 1 1 3.3 2.1c-.6.3-1 .8-1 1.4v.3" fill="none" stroke="#1d1d1f" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="14.7" r="1.1" fill="#1d1d1f"/>',
  xoct: '<path d="M8.2 2.5h7.6l5.7 5.7v7.6l-5.7 5.7H8.2l-5.7-5.7V8.2z" fill="currentColor"/><path d="M9 9l6 6M15 9l-6 6" stroke="#1d1d1f" stroke-width="2.1" stroke-linecap="round"/>',
  turn: F('<path d="M9.6 4.2 3 10l6.6 5.8V12c4.6 0 8 1.2 10.4 5.3 0-6-3.3-9.6-10.4-10z"/>'),
  wifi: L('<path d="M2.6 9a13.8 13.8 0 0 1 18.8 0M5.8 12.5a9.2 9.2 0 0 1 12.4 0M9 15.9a4.5 4.5 0 0 1 6 0"/>', 2) + F('<circle cx="12" cy="19.2" r="1.5"/>'),
  wifiex: L('<path d="M2.6 9a13.8 13.8 0 0 1 14.4-2.6M5.8 12.5a9.2 9.2 0 0 1 8.8-2.3M9 15.9a4.5 4.5 0 0 1 4.4-1.2M20.2 8.4v6"/>', 2) + F('<circle cx="12" cy="19.2" r="1.5"/><circle cx="20.2" cy="18" r="1.3"/>'),
  wifislash: L('<path d="M2.6 9a13.8 13.8 0 0 1 18.8 0M5.8 12.5a9.2 9.2 0 0 1 12.4 0M9 15.9a4.5 4.5 0 0 1 6 0" opacity=".45"/><path d="M4 3.5l16 17"/>', 2) + F('<circle cx="12" cy="19.2" r="1.5" opacity=".45"/>'),
  cloudx: L('<path d="M7 18.5h10.4a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.6 9.1 4.7 4.7 0 0 0 7 18.5z"/><path d="M12 9.6v4"/>', 1.7) + F('<circle cx="12" cy="16" r="1"/>'),
  clockex: L('<circle cx="11" cy="12" r="8"/><path d="M11 7.5V12l3 2"/><path d="M20.5 3.5v5"/>', 1.7) + F('<circle cx="20.5" cy="11.4" r="1.1"/>'),
  loc: F('<path d="M20.6 3.4 3.8 10.6c-.8.4-.7 1.5.1 1.7l6.6 1.6 1.6 6.6c.2.8 1.3.9 1.7.1z"/>'),
  locline: L('<path d="M20.6 3.4 3.8 10.6l7.4 2.2 2.2 7.4z"/>', 1.6),
  locslash: F('<path d="M20.6 3.4 3.8 10.6c-.8.4-.7 1.5.1 1.7l6.6 1.6 1.6 6.6c.2.8 1.3.9 1.7.1z" opacity=".55"/>') + L('<path d="M3.5 3.5l17 17"/>', 2),
  shield: F('<path d="M12 2.5 4.5 5.4v6c0 4.6 3.1 8.6 7.5 10.1 4.4-1.5 7.5-5.5 7.5-10.1v-6z"/>') + '<path d="m8.4 12.1 2.5 2.5 4.8-5.2" fill="none" stroke="#1d1d1f" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>',
  shieldline: L('<path d="M12 2.8 4.6 5.6v5.8c0 4.5 3 8.4 7.4 9.9 4.4-1.5 7.4-5.4 7.4-9.9V5.6z"/>', 1.6),
  zzz: L('<path d="M4 7h5l-5 6h5M12.5 11.5h4l-4 5h4M17.5 4h3l-3 3.6h3"/>', 1.6),
  gauge: L('<circle cx="12" cy="12" r="8.6"/><path d="M12 12l3.6-3.6"/><path d="M7 15.5h.01M6.4 11h.01M8.6 7.2h.01M12 6h.01M17.6 11h.01M17 15.5h.01"/>', 1.6),
  grid: L('<rect x="3.6" y="3.6" width="7" height="7" rx="1.8"/><rect x="13.4" y="3.6" width="7" height="7" rx="1.8"/><rect x="3.6" y="13.4" width="7" height="7" rx="1.8"/><rect x="13.4" y="13.4" width="7" height="7" rx="1.8"/>', 1.5),
  radio: L('<path d="M8.4 8.4a5.1 5.1 0 0 0 0 7.2M15.6 8.4a5.1 5.1 0 0 1 0 7.2M5.5 5.5a9.2 9.2 0 0 0 0 13M18.5 5.5a9.2 9.2 0 0 1 0 13"/>', 1.6) + F('<circle cx="12" cy="12" r="2.1"/>'),
  sidebar: L('<rect x="3" y="4.5" width="18" height="15" rx="3.2"/><path d="M9.5 4.5v15M5.6 8h1.6M5.6 10.8h1.6"/>', 1.5),
  compass: L('<circle cx="12" cy="12" r="9"/><path d="M15.8 8.2 13.6 13.6 8.2 15.8l2.2-5.4z"/>', 1.6),
  arrows: L('<path d="M4.5 8.2h14.5l-3.4-3.4M19.5 15.8H5l3.4 3.4"/>', 1.7),
  ecg: L('<path d="M2.5 12.5h4.2l2-5.5 3.6 11 2.4-7.5 1.6 2h5.2"/>', 1.6),
  info: L('<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/>', 1.6) + F('<circle cx="12" cy="7.8" r="1.1"/>'),
  clock: L('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.4 2"/>', 1.6),
  bubble: L('<path d="M4.5 4h15a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H11l-4.5 3.4V17h-2a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM7.5 9h9M7.5 12.4h6"/>', 1.5),
  tools: L('<path d="M14.5 6.2a4 4 0 0 0 5 5L11 19.7a2.1 2.1 0 0 1-3-3zM4 4l4.4 4.4M3.5 8l2-2.2"/>', 1.6),
  doc: L('<path d="M6.5 3.5h7l4.5 4.5v12.5h-11.5zM13.5 3.5V8H18"/>', 1.6),
  fan: L('<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><path d="M7.7 7.6 10.6 16M16.3 7.6 13.4 16M8.2 6h7.6"/>', 1.5),
  xcircle: L('<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>', 1.6),
  branch: L('<circle cx="7" cy="5.6" r="2.2"/><circle cx="7" cy="18.4" r="2.2"/><circle cx="17" cy="8" r="2.2"/><path d="M7 7.8v8.4M17 10.2c0 4-10 2.4-10 6"/>', 1.5),
  bars: L('<path d="M5 20V12M9.7 20V5M14.3 20v-9M19 20v-5M3 20.5h18"/>', 1.9),
  dollar: L('<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2c-.4-1-1.4-1.6-2.8-1.6-1.6 0-2.8.8-2.8 2.1 0 2.9 5.8 1.5 5.8 4.5 0 1.3-1.2 2.2-3 2.2-1.5 0-2.6-.7-3-1.8M12 6v1.6M12 16.4V18"/>', 1.5),
  down: L('<path d="M12 5v13M6.5 12.5 12 18l5.5-5.5"/>', 2),
  cup: L('<path d="M3.5 10h13v3.5a5 5 0 0 1-5 5h-3a5 5 0 0 1-5-5z"/><path d="M16.5 11.4h1.4a2.2 2.2 0 0 1 0 4.4h-1.6M2.5 21h16"/>', 1.5),
  handle: L('<path d="M5 9h14M5 12h14M5 15h14"/>', 1.4),
  copy: L('<rect x="8.5" y="8.5" width="11" height="11" rx="2.6"/><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/>', 1.6),
  github: F('<path d="M12 2.2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.3-3.4-1.3-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.4 1.1 2.9.8.1-.7.4-1.1.6-1.3-2.2-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1a9.6 9.6 0 0 1 5 0c1.9-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0 0 12 2.2z"/>'),
  lock: L('<rect x="5" y="10.5" width="14" height="10" rx="2.6"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>', 1.6),
  key: L('<circle cx="8" cy="15" r="4.4"/><path d="M11.2 11.8l8.3-8.3M16.5 6.5l2.5 2.5M14 9l2 2"/>', 1.6),
  eye: L('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>', 1.6),
  hush: L('<path d="M12 3.2 4.8 6v5.6c0 4.4 3 8.1 7.2 9.6 4.2-1.5 7.2-5.2 7.2-9.6V6z"/><path d="M9 9l6 6M15 9l-6 6"/>', 1.6),
  two: L('<rect x="3.5" y="6" width="17" height="12" rx="3.2"/><path d="m7.4 12 1.9 1.9 3.2-3.6M13.9 12l1.5 1.5 2.6-3"/>', 1.6),
  hold: L('<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4.2h-4.2"/><path d="M12 8.6V12l2.2 1.6"/>', 1.6),
  bolt: F('<path d="M13.5 2.5 4.8 13.4h6l-1.3 8.1 8.7-10.9h-6z"/>'),
  leaf: L('<path d="M5 19c0-8 5-13.5 15-14-.4 9.8-6 14.6-14 14z"/><path d="M5 19c3-4 6-6.6 9.5-8.6"/>', 1.6),
  thermo: L('<path d="M10 4.8a2 2 0 0 1 4 0v9.3a4 4 0 1 1-4 0z"/><path d="M12 10v6.5"/>', 1.6),
  cpu: L('<rect x="6" y="6" width="12" height="12" rx="2.4"/><rect x="9.4" y="9.4" width="5.2" height="5.2" rx="1"/><path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/>', 1.5),
  memory: L('<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 7v10M11 7v10M15 7v10M5 19.5v-2.5M19 19.5v-2.5"/>', 1.4),
  speed: L('<path d="M4.2 16.6a8.6 8.6 0 1 1 15.6 0"/><path d="M12 13.4l4.6-4.4"/>', 1.7) + F('<circle cx="12" cy="13.6" r="1.6"/>'),
  sparkle: F('<path d="M12 2.8c.5 4.6 2.6 6.7 7.2 7.2-4.6.5-6.7 2.6-7.2 7.2-.5-4.6-2.6-6.7-7.2-7.2 4.6-.5 6.7-2.6 7.2-7.2zM18.6 15.4c.25 2 1.1 2.85 3.1 3.1-2 .25-2.85 1.1-3.1 3.1-.25-2-1.1-2.85-3.1-3.1 2-.25 2.85-1.1 3.1-3.1z"/>'),
  plug: L('<path d="M8 3v5M16 3v5M6 8h12v3.5a6 6 0 0 1-12 0zM12 17.5V21"/>', 1.6),
  apple: L('<rect x="5" y="3" width="14" height="18" rx="3.4"/><path d="M10 6h4"/>', 1.5),
  slider: L('<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>', 1.6),
  stack: L('<path d="M12 3.5 21 8l-9 4.5L3 8z"/><path d="m3 12 9 4.5 9-4.5M3 16l9 4.5 9-4.5"/>', 1.5),
  claude: F('<path d="M12 2.6l1.55 6.05 5.2-3.55-3.55 5.2 6.05 1.55-6.05 1.55 3.55 5.2-5.2-3.55L12 21.4l-1.55-6.05-5.2 3.55 3.55-5.2L2.75 12.15l6.05-1.55-3.55-5.2 5.2 3.55z"/>'),
  q: L('<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.4v.4"/>', 1.6) + F('<circle cx="12" cy="16.6" r="1.05"/>'),
  windows: F('<path d="M3 3h8.4v8.4H3zM12.6 3H21v8.4h-8.4zM3 12.6h8.4V21H3zM12.6 12.6H21V21h-8.4z"/>'),
  tux: F('<path fill-rule="evenodd" d="M12 1.8c-2.4 0-3.7 1.9-3.7 4.4 0 1.4-.4 2.3-1.3 3.7-1.3 1.9-2.4 3.9-2.1 6.4.2 1.7 1.1 2.7 2.1 3.3h9.9c1.1-.6 2-1.6 2.2-3.3.3-2.5-.8-4.5-2.1-6.4-.9-1.4-1.3-2.3-1.3-3.7 0-2.5-1.3-4.4-3.7-4.4zm0 7.8c-1.9 0-3.4 2.4-3.4 5.2 0 2.4 1.4 4 3.4 4s3.4-1.6 3.4-4c0-2.8-1.5-5.2-3.4-5.2zM9.85 5.6a.75.75 0 1 0 1.5 0 .75.75 0 1 0-1.5 0zm2.8 0a.75.75 0 1 0 1.5 0 .75.75 0 1 0-1.5 0zM10.7 7.3h2.6L12 8.7z"/><path d="M5.5 19.5c0-.9 1.5-1.3 3.1-.9l1.8.6c.7.3.6 1.4-.3 1.6l-3 .5c-1 .1-1.6-.8-1.6-1.8zm13 0c0-.9-1.5-1.3-3.1-.9l-1.8.6c-.7.3-.6 1.4.3 1.6l3 .5c1 .1 1.6-.8 1.6-1.8z"/>'),
  macos: F('<path d="M16.4 12.7c0-2.6 2.1-3.8 2.2-3.9-1.2-1.8-3.1-2-3.8-2-1.6-.2-3.1.9-3.9.9s-2-.9-3.4-.9c-1.7 0-3.3 1-4.2 2.6-1.8 3.1-.5 7.8 1.3 10.3.9 1.2 1.9 2.6 3.2 2.6 1.3-.1 1.8-.8 3.3-.8s2 .8 3.4.8c1.4 0 2.3-1.3 3.1-2.5 1-1.4 1.4-2.8 1.4-2.9 0 0-2.6-1-2.6-4.2zM13.9 5c.7-.9 1.2-2 1-3.2-1 0-2.3.7-3 1.5-.7.8-1.2 2-1.1 3.1 1.1.1 2.3-.6 3.1-1.4z"/>'),
};
TW.SF = SF;
const sym = (n, cls = '') => `<svg class="sf ${cls}" viewBox="0 0 24 24" aria-hidden="true"><use href="#sf-${n}"/></svg>`;
TW.sym = sym;
(function sprite() {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('aria-hidden', 'true'); s.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
  s.innerHTML = '<defs>' + Object.entries(SF).map(([k, v]) => `<symbol id="sf-${k}" viewBox="0 0 24 24" overflow="visible">${v}</symbol>`).join('') + '</defs>';
  (document.body || document.documentElement).prepend(s);
})();
/* the waveform symbol, with SF's variable-colour sweep */
const wave = (cls = '') => `<svg class="sf wv ${cls}" viewBox="0 0 24 24" aria-hidden="true">${[[4, 11, 13], [7.5, 8, 16], [11, 4.5, 19.5], [14.5, 7.5, 16.5], [18, 9.5, 14.5], [21, 11, 13]].map(([x, a, b], i) => `<path d="M${x} ${a}V${b}" style="--i:${i}" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`).join('')}</svg>`;
TW.wave = wave;
function hydrateSymbols(root = document) {
  $$('[data-sf]', root).forEach(e => { const n = e.dataset.sf; e.removeAttribute('data-sf'); e.insertAdjacentHTML('afterbegin', n === 'wave' ? wave() : sym(n)); });
}
TW.hydrate = hydrateSymbols;

/* flags: drawn, so they read the same on every platform */
const FLAG = {
  CA: '<svg class="flag" viewBox="0 0 40 20" aria-hidden="true"><rect width="40" height="20" fill="#fff"/><rect width="10" height="20" fill="#d52b1e"/><rect x="30" width="10" height="20" fill="#d52b1e"/><path fill="#d52b1e" d="M20 3.2l1.2 2.3c.1.2.3.2.5.1l1-.6-.6 3.2c-.1.4.3.5.5.3l1.3-1.5.4.8c.1.2.2.2.4.2l1.5-.3-.5 1.7c-.1.2 0 .3.2.4l.6.3-3 2.4c-.2.2-.2.3-.1.5l.3.9-2.8-.5c-.2 0-.3.1-.3.3l.1 3.1h-.7l.1-3.1c0-.2-.1-.3-.3-.3l-2.8.5.3-.9c.1-.2.1-.3-.1-.5l-3-2.4.6-.3c.2-.1.3-.2.2-.4l-.5-1.7 1.5.3c.2 0 .3 0 .4-.2l.4-.8 1.3 1.5c.2.2.6.1.5-.3l-.6-3.2 1 .6c.2.1.4.1.5-.1z"/></svg>',
  US: '<svg class="flag" viewBox="0 0 38 20" aria-hidden="true"><rect width="38" height="20" fill="#fff"/>' + [0, 2, 4, 6, 8, 10, 12].map(i => `<rect y="${(i * 20 / 13).toFixed(2)}" width="38" height="${(20 / 13).toFixed(2)}" fill="#b22234"/>`).join('') + '<rect width="15.2" height="10.77" fill="#3c3b6e"/></svg>',
};
TW.flag = cc => FLAG[cc] || '';

/* ══════════════════════════ the marks ══════════════════════════
   src/Glyph.swift, line for line, on a canvas in the shared 0…100 box. */
const AMBER = [230, 169, 60], TRED = [229, 72, 77];
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
function circ(g, x, y, r) { g.beginPath(); g.arc(x, y, Math.max(r, 0), 0, Math.PI * 2); }
function drawRadar(g, st, P, col, awake, reduce) {
  const A = reduce ? 0 : 1, rot = (d, f) => { g.save(); g.translate(50, 50); g.rotate(d * Math.PI / 180); g.translate(-50, -50); f(); g.restore(); };
  let rc = col, dash = [];
  if (st === 'off') { rc = TRED; dash = [5, 7]; } else if (st === 'holdNet') { rc = AMBER; dash = [5, 6]; } else if (st === 'holdGeo') rc = AMBER;
  g.lineWidth = 6; g.strokeStyle = rgba(rc, 1); g.setLineDash(dash); circ(g, 50, 50, 33); g.stroke(); g.setLineDash([]);
  if (st === 'verify') rot((P * 150) % 360, () => {
    g.beginPath(); g.moveTo(50, 50);
    for (let i = 0; i <= 12; i++) { const a = (270 + (208.5 - 270) * i / 12) * Math.PI / 180; g.lineTo(50 + 33 * Math.cos(a), 50 + 33 * Math.sin(a)); }
    g.closePath(); g.fillStyle = rgba(col, .16); g.fill();
    g.beginPath(); g.moveTo(50, 50); g.lineTo(50, 17); g.lineWidth = 4; g.lineCap = 'round'; g.strokeStyle = rgba(col, 1); g.stroke();
  });
  if (st === 'clear') {
    const pr = A ? (P * .42) % 1 : 0, r = A ? 8 + pr * 26 : 22, op = A ? (1 - pr) * .5 : .3;
    g.lineWidth = 3; g.strokeStyle = rgba(col, op); circ(g, 50, 50, r); g.stroke();
  }
  if (st === 'holdNet') for (let i = 0; i < 2; i++) {
    const pr = A ? ((P * .7) + i * .5) % 1 : 0, r = A ? 7 + pr * 15 : 11 + i * 7, op = A ? Math.max(0, 1 - pr) * .7 : .55 - i * .25;
    g.lineWidth = 3.5; g.strokeStyle = rgba(AMBER, op); circ(g, 50, 50, r); g.stroke();
  }
  [[64, 41], [38, 58], [58, 66]].forEach(([x, y], i) => {
    const op = st === 'clear' ? .8 + .2 * Math.sin(P * 1.6 + i * 1.3) * A : st === 'verify' ? .3 + .12 * Math.sin(P * 2.2 + i) * A : st === 'off' ? .22 : 0;
    if (op > .001) { g.fillStyle = rgba(col, op); circ(g, x, y, 3.6); g.fill(); }
  });
  if (st === 'holdGeo') {
    rot((P * 45) % 360, () => { g.lineWidth = 3; g.strokeStyle = rgba(AMBER, 1); g.setLineDash([4, 5]); circ(g, 50, 50, 15); g.stroke(); g.setLineDash([]); });
    g.beginPath(); g.moveTo(50, 50); g.lineTo(72, 32); g.lineWidth = 2.5; g.lineCap = 'round'; g.setLineDash([2, 4]); g.strokeStyle = rgba(AMBER, 1); g.stroke(); g.setLineDash([]);
    const dx = -.773, dy = .634, lunge = A ? 6 * (.5 + .5 * Math.sin(P * 2.2)) : 0, s = 1 + (A ? .16 * Math.sin(P * 3) : 0);
    const mx = 72 + dx * lunge, my = 32 + dy * lunge;
    g.fillStyle = rgba(AMBER, 1); circ(g, mx, my, 5 * s); g.fill();
    const hp = A ? (P * 1.1) % 1 : 0, hr = A ? 5 + hp * 9 : 10, hop = A ? (1 - hp) * .8 : .5;
    g.lineWidth = 2.5; g.strokeStyle = rgba(AMBER, hop); circ(g, mx, my, hr); g.stroke();
  }
  if (awake) {
    const breathing = awake === 2, amp = breathing ? 1 : .6, br = (breathing && !reduce) ? .5 + .5 * Math.sin(P * 2 * Math.PI / 2.4) : .7;
    [[15, .09], [11, .15], [7.5, .22]].forEach(([r, op]) => { g.fillStyle = rgba(col, op * (.75 + .35 * br * amp)); circ(g, 50, 50, r); g.fill(); });
    g.lineWidth = 2.2; g.strokeStyle = rgba(col, .44 + .3 * br * amp); circ(g, 50, 50, 9.5 + 1.7 * br * amp); g.stroke();
  }
  if (st === 'off') { g.lineWidth = 4; g.strokeStyle = rgba(TRED, 1); circ(g, 50, 50, 5.5); g.stroke(); }
  else { g.fillStyle = rgba(st === 'holdNet' ? AMBER : col, 1); circ(g, 50, 50, awake ? 5.6 : 4.5); g.fill(); }
}
function drawModel(g, tier, P, E, col) {
  const stroke = (w) => { g.lineWidth = w; g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = rgba(col, 1); g.stroke(); };
  const rs = (deg, k, f) => { g.save(); g.translate(50, 50); g.rotate(deg * Math.PI / 180); g.scale(k, k); g.translate(-50, -50); f(); g.restore(); };
  if (tier === 'haiku') rs(E * 6 * Math.sin(P * .7), 1, () => {
    for (let k = 0; k < 3; k++) {
      const a = (-90 + k * 120) * Math.PI / 180, dx = Math.cos(a), dy = Math.sin(a), off = E * 3.4 * (.5 + .5 * Math.sin(P * 2.3 + k * 2.094));
      g.beginPath(); g.moveTo(50 + dx * (16 + off), 50 + dy * (16 + off)); g.lineTo(50 + dx * (34 + off), 50 + dy * (34 + off)); stroke(8);
    }
    g.fillStyle = rgba(col, 1); circ(g, 50, 50, 7 * (1 + E * .22 * Math.sin(P * 3))); g.fill();
  });
  else if (tier === 'sonnet') rs(E * (P * 16) + E * 4 * Math.sin(P * 1.3), 1 + E * .05 * Math.sin(P * 1.3), () => {
    g.beginPath();
    for (let i = 0; i <= 24; i++) { const a = (-90 + i / 24 * 180) * Math.PI / 180, x = 50 + 12.5 * Math.cos(a), y = 37.5 + 12.5 * Math.sin(a); i ? g.lineTo(x, y) : g.moveTo(x, y); }
    for (let i = 0; i <= 24; i++) { const a = (-90 - i / 24 * 180) * Math.PI / 180; g.lineTo(50 + 12.5 * Math.cos(a), 62.5 + 12.5 * Math.sin(a)); }
    stroke(8);
  });
  else if (tier === 'opus') {
    const radii = [16, 27, 38], gaps = [90, 210, 330], rates = [14, -10, 8];
    for (let i = 0; i < 3; i++) rs(E * (P * rates[i]), 1 + E * .06 * Math.sin(P * 1.7 - i * .8), () => {
      g.beginPath(); g.arc(50, 50, radii[i], (gaps[i] + 30) * Math.PI / 180, (gaps[i] + 330) * Math.PI / 180); stroke(6.5);
    });
    g.fillStyle = rgba(col, 1); circ(g, 50, 50, 5 * (1 + E * .18 * Math.sin(P * 2.1))); g.fill();
  } else {
    const sp = f => { const a = f * 2.35 * 2 * Math.PI - Math.PI / 2, r = 2.5 + 32.5 * f; return [50 + r * Math.cos(a), 50 + r * Math.sin(a)]; };
    g.beginPath(); for (let i = 0; i <= 120; i++) { const [x, y] = sp(i / 120); i ? g.lineTo(x, y) : g.moveTo(x, y); } stroke(8);
    if (E > .01) {
      const head = (P * .22) % 1, tail = Math.max(0, head - .16);
      g.beginPath(); let first = true; for (let f = tail; f <= head; f += .01) { const [x, y] = sp(f); first ? g.moveTo(x, y) : g.lineTo(x, y); first = false; }
      g.lineWidth = 8.6; g.strokeStyle = rgba(col, Math.min(1, E) * .95); g.stroke();
      const [hx, hy] = sp(head); g.fillStyle = rgba(col, Math.min(1, E)); circ(g, hx, hy, 5); g.fill();
    }
    g.fillStyle = rgba(col, 1); circ(g, 50, 50, 4); g.fill();
  }
}
function drawBeacon(g, mode, P, col, reduce) {
  const on = mode > 0, breathing = mode === 2, amp = breathing ? 1 : .6, br = (breathing && !reduce) ? .5 + .5 * Math.sin(P * 2 * Math.PI / 2.4) : .7;
  if (on) {
    [[30, .1], [21, .17], [13, .26]].forEach(([r, op]) => { g.fillStyle = rgba(col, op * (.75 + .35 * br * amp)); circ(g, 50, 50, r); g.fill(); });
    g.lineWidth = 4.5; g.strokeStyle = rgba(col, .3 + .25 * br * amp); circ(g, 50, 50, 17 + 2 * br * amp); g.stroke();
    g.fillStyle = rgba(col, 1); circ(g, 50, 50, 11); g.fill();
  } else {
    g.lineWidth = 4.5; g.strokeStyle = rgba(col, .34); circ(g, 50, 50, 15); g.stroke();
    g.fillStyle = rgba(col, .3); circ(g, 50, 50, 6); g.fill();
  }
}

/* One registry: a mark is drawn only while it is on screen, and the loop
   stops when nothing visible has anything to say or the tab is hidden. */
const MARKS = new Set(), TICKS = new Set();
const seen = new IntersectionObserver(es => { for (const e of es) { const m = e.target.__m; if (m) m.on = e.isIntersecting; const k = e.target.__tk; if (k) k.forEach(t => t.on = e.isIntersecting); } wake(); }, { rootMargin: '80px' });
function parseColor(c) { const m = c.match(/[\d.]+/g); return m ? [+m[0], +m[1], +m[2]] : [235, 235, 235]; }
function mount(host, kind, get, opt = {}) {
  const cv = document.createElement('canvas'); cv.setAttribute('aria-hidden', 'true');
  cv.style.cssText = 'display:block;width:100%;height:100%';
  host.appendChild(cv);
  const m = { host, cv, g: cv.getContext('2d'), kind, get, k: opt.k || 1, on: OG, col: null, px: 0, dirty: true };
  cv.__m = m; MARKS.add(m); if (!OG) seen.observe(cv);
  return m;
}
function paint(m, P) {
  const r = m.host.clientWidth || parseFloat(m.host.style.width) || 20, dpr = Math.max(2, devicePixelRatio || 1) * m.k, px = Math.ceil(r * dpr);
  if (px !== m.px) { m.cv.width = m.cv.height = px; m.px = px; }
  if (!m.col || m.dirty) m.col = parseColor(getComputedStyle(m.host).color);
  const g = m.g, p = m.get(); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, px, px); g.scale(px / 100, px / 100);
  const rd = REDUCE || p.still;
  if (m.kind === 'radar') drawRadar(g, p.state, rd ? 0 : P, m.col, p.awake || 0, rd);
  else if (m.kind === 'model') drawModel(g, p.tier, rd ? 0 : P, p.working && !rd ? 1 : 0, m.col);
  else drawBeacon(g, p.mode || 0, rd ? 0 : P, m.col, rd);
  m.dirty = false;
}
const live = m => { if (REDUCE) return false; const p = m.get(); return !p.still && (m.kind === 'radar' ? true : m.kind === 'model' ? !!p.working : p.mode === 2); };
TW.radar = (host, get, opt) => mount(host, 'radar', typeof get === 'function' ? get : () => ({ state: get || 'clear', ...(opt || {}) }), opt);
TW.model = (host, tier, working = true, opt) => mount(host, 'model', typeof tier === 'function' ? tier : () => ({ tier, working }), opt);
TW.beacon = (host, get, opt) => mount(host, 'beacon', typeof get === 'function' ? get : () => ({ mode: get }), opt);
TW.drawAll = P => { for (const m of MARKS) if (m.cv.isConnected) paint(m, P); };
TW.dirty = () => MARKS.forEach(m => m.dirty = true);
/* a ticker runs while its element is on screen; return true to keep going */
TW.ticker = (elm, fn) => { const t = { fn, on: false }; (elm.__tk ||= []).push(t); TICKS.add(t); seen.observe(elm); return t; };
let raf = 0, t0p = performance.now();
const phase = () => (performance.now() - t0p) / 1000;
function frame() {
  raf = 0; if (OG) return;
  const P = phase(); let more = false;
  for (const t of TICKS) if (t.on && t.fn(P) !== false) more = true;
  for (const m of MARKS) {
    if (!m.cv.isConnected) { MARKS.delete(m); continue; }
    if (!m.on) continue;
    const lv = live(m), key = JSON.stringify(m.get());
    if (lv) { paint(m, P); more = true; m.key = key; } else if (m.dirty || m.key !== key) { paint(m, P); m.key = key; }
  }
  if (more && !document.hidden) raf = requestAnimationFrame(frame);
}
function wake() { if (!raf && !document.hidden && !OG) raf = requestAnimationFrame(frame); }
TW.wake = wake;
document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });

/* ══════════════════════════ a working day ══════════════════════════
   One fictional product team (site/tools/fixture.py feeds the terminal
   frames from the same day), so the numbers agree on every surface. */
const D = TW.day = {
  plan: { session: [34, '2h 14m'], week: [47, '2d 4h'], fable: [22, '2d 4h'] },
  loc: { city: 'Toronto, Ontario', isp: 'Bell Canada', ip: '142.114.9.2' },
  away: { city: 'Seattle, Washington', isp: 'Lumen', ip: '63.141.22.9' },
  cost: '$44',
};
const AG = TW.agents = {
  pipe: { name: 'data-pipeline', tier: 'opus', meta: 'Opus 5.5 · High', warn: true, turn: 2280, act: 'waiting on 2 subagents…', tools: 301,
    subs: [['general-purpose', "backfill September's partitions", 1, 900], ['general-purpose', 'add a test for late events', 1, 300], ['Explore', 'trace the late-arriving events', 0, 2000]], more: '+1 more' },
  ledger: { name: 'ledger-api', tier: 'fable', meta: 'Fable 5.1 · Max', turn: 1480, act: 'Running psql -f migrations/0042_split_ledger.sql', tooling: true, tools: 212, title: 'Split the ledger table by currency' },
  infra: { name: 'infra', tier: 'sonnet', meta: 'Sonnet 5.5 · High', turn: 520, act: 'thinking…', tools: 41 },
  checkout: { name: 'checkout-web', tier: 'opus', meta: 'Opus 5.5 · High', turn: 1260, act: 'Running pnpm test payments', tooling: true, tools: 148,
    subs: [['code-reviewer', 'review the refund diff', 1, 420], ['test-runner', 'run the payments suite', 1, 150], ['Explore', 'map every caller of chargeCustomer', 0, 1100]] },
};

/* ══════════════════════════ the popover ══════════════════════════ */
const spinner = '<svg class="spin" viewBox="0 0 20 20" aria-hidden="true">' + [...Array(8)].map((_, i) => `<rect x="9.1" y="1.5" width="1.8" height="5" rx=".9" fill="currentColor" opacity="${(.25 + .75 * (i / 7)).toFixed(2)}" transform="rotate(${i * 45} 10 10)"/>`).join('') + '</svg>';
function treeHTML(subs, more, base) {
  const rows = subs.map((s, i) => `<div class="n${s[2] ? '' : ' fin'}${!more && i === subs.length - 1 ? ' last' : ''}"><span class="rail">${s[2] ? '<i class="dot"></i>' : `<i class="dot ok">${sym('check')}</i>`}</span><span class="c"><span class="ty">${s[0]}</span><span class="d">${s[1]}</span><span class="e" data-since="${s[3]}">${elapsed(s[3])}</span></span></div>`).join('');
  return `<div class="tree">${rows}${more ? `<div class="n mr last"><span class="rail"></span><span class="more">${more}</span></div>` : ''}</div>`;
}
function rowHTML(a, key) {
  return `<div class="pv-row" data-row="${key}"><div class="r1"><div class="gl" data-mark="${a.tier}"></div><div class="col">
    <div class="ln"><span class="nm">${a.name}</span><span class="mm">${a.meta}</span>${a.warn ? `<span class="wn">${sym('warn')}</span>` : ''}<span class="ck" data-turn="${a.turn}">${elapsed(a.turn)}</span></div>
    <div class="ln">${a.tooling ? spinner : ''}<span class="act${a.tooling ? ' shim' : ''}">${a.act}</span><span class="tl">${fmt(a.tools)} tools</span></div></div></div>
    ${a.subs ? treeHTML(a.subs, a.more) : ''}</div>`;
}
const NY = {
  pending_tool: ['hand', 'var(--orange)', 'waiting for approval'], asking: ['qbubble', 'var(--indigo)', 'asked you a question'],
  failed: ['xoct', 'var(--red)', 'failed'], done: [null, 'var(--green)', 'done — your turn'],
};
function nyHTML(a, kind, sub, agoS) {
  const [s, c] = NY[kind];
  const icon = s ? `<span class="sy" style="color:${c}">${sym(s)}</span>` : `<span class="sy done"><svg viewBox="0 0 16 16" width="16" height="16"><circle cx="8" cy="8" r="7.25" fill="none" stroke="var(--green)" stroke-width="1.5"/><path class="ckp" d="M4.2 8.6l2.9 2.9 5-6.4" fill="none" stroke="var(--green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" pathLength="1"/></svg></span>`;
  return `<div class="pv-row ny" data-ny="${kind}">${icon}<div class="col"><div class="ln"><span class="nm">${a.name}</span><span class="mm">${a.meta}</span></div><div class="ln"><span class="act">${sub}</span></div></div><span class="ago">${agoS}</span></div>`;
}
function ringSVG(f, warn) {
  const r = 14.75, c = 2 * Math.PI * r, tint = warn || 'rgb(255 255 255/.92)';
  return `<svg viewBox="0 0 34 34"><circle cx="17" cy="17" r="${r}" fill="none" stroke="${warn ? warn : 'rgb(255 255 255)'}" stroke-opacity=".14" stroke-width="4.5"/><circle class="arc" cx="17" cy="17" r="${r}" fill="none" stroke="${tint}" stroke-width="4.5" stroke-linecap="round" transform="rotate(-90 17 17)" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${(c * (1 - Math.max(f, .004))).toFixed(2)}" data-c="${c.toFixed(3)}"/></svg>`;
}
TW.ringSVG = ringSVG;
const setRing = (svgArc, f) => { const c = +svgArc.dataset.c; svgArc.setAttribute('stroke-dashoffset', (c * (1 - clamp(Math.max(f, .004)))).toFixed(2)); };
TW.setRing = setRing;
const tint = p => p >= 85 ? 'var(--red)' : p >= 60 ? 'var(--yellow)' : null;
function planHTML() {
  const ring = (l, [p, r]) => `<div class="ringc" data-pct="${p}"><div class="ring">${ringSVG(p / 100, tint(p))}<span class="n">${p}</span></div><div><div class="l">${l}</div><div class="rs">${sym('refresh')}${r}</div></div></div>`;
  const bar = (l, [p, r]) => `<div class="barc" data-pct="${p}"><div class="bh"><span class="l">${l}</span><span class="rs">${sym('refresh')}${r}</span><span class="p">${p}%</span></div><div class="bt"><i style="width:${p}%"></i></div></div>`;
  return { rings: ring('Session', D.plan.session) + ring('Weekly', D.plan.week) + ring('Fable', D.plan.fable), bars: bar('Session', D.plan.session) + bar('Weekly', D.plan.week) + bar('Fable', D.plan.fable) };
}
/* the whole popover. o.show: which movable sections are on; o.dyn: hero/og slots */
function popoverHTML(o = {}) {
  const pl = planHTML();
  const on = s => (o.show || ['net', 'agents', 'location', 'keepawake', 'plan']).includes(s) ? '' : ' off';
  const order = o.order || ['net', 'agents', 'location', 'apps', 'plan', 'keepawake'];
  const sec = {
    net: `<div class="stkh" data-k="net"><div class="pv-net"><span class="rg">${sym('globe')}<span class="l">Internet</span><span class="v" data-k="int">11</span><span class="u">ms</span></span><span class="rg">${sym('rack')}<span class="l">API</span><span class="v" data-k="api">214</span><span class="u">ms</span></span></div>
      <div class="pv-ban rd">${sym('wifislash')}<div><b>Your internet is offline</b><span>Claude errors are local — not Anthropic</span></div></div></div>`,
    agents: `<div class="pv-ah"><span class="pv-cap">AGENTS</span><span class="cnt"><span class="hand" data-k="hand">${sym('hand')}1</span><span>${wave()}<span data-k="nwork">3</span></span><span class="dn">${sym('checkf')}41</span></span></div>
      <div class="slot" data-slot="ny">${nyHTML(AG.ledger, 'pending_tool', 'waiting for approval · ' + AG.ledger.title, '0s')}</div>
      <div class="slot" data-slot="pipe">${rowHTML(AG.pipe, 'pipe')}</div>
      <div class="slot" data-slot="ledger">${rowHTML(AG.ledger, 'ledger')}</div>
      <div class="slot" data-slot="infra">${rowHTML(AG.infra, 'infra')}</div>
      <div class="pv-rest">${sym('chev')}<span>Resting · 2</span></div>`,
    location: `<div class="stkh" data-k="loc">
      <div class="pv-loc"><span class="tile">${FLAG.CA}<span class="bdg" style="color:var(--green)">${sym('checkf')}</span></span><span class="col"><span class="t">${D.loc.city}</span><span class="s sub">Inside Canada<i>  ·  ${D.loc.isp}</i></span></span><span class="ip">${D.loc.ip}</span><span class="rbtn">${sym('refresh')}</span></div>
      <div class="pv-loc"><span class="tile">${FLAG.US}<span class="bdg" style="color:var(--orange)">${sym('exf')}</span></span><span class="col"><span class="t">${D.away.city}</span><span class="s sub"><em style="font-style:normal;color:var(--orange)">Outside Canada — Claude is held</em><i>  ·  ${D.away.isp}</i></span></span><span class="ip">${D.away.ip}</span><span class="rbtn">${sym('refresh')}</span></div>
      <div class="pv-loc"><span class="tile">${FLAG.CA}</span><span class="col"><span class="t">Location unknown</span><span class="s sub">Internet down — Claude is held until it's back</span></span><span class="rbtn">${sym('refresh')}</span></div></div>`,
    apps: `<div class="pv-app"><span class="tile app cl">${sym('claude')}</span><span class="col"><span class="t">Claude Desktop</span><span class="s sub">Chats + Claude Code, through the guard</span></span><span class="open">Open</span></div>
      <div class="pv-app"><span class="tile app wb">${sym('globe')}</span><span class="col"><span class="t">Claude on the web</span><span class="s sub">claude.ai in a guarded Google Chrome window</span></span><span class="open">Open</span></div>`,
    plan: `<div class="pv-plan"><div class="h"><span class="pv-cap">PLAN USAGE</span><span class="r" data-k="planh">${D.cost} today · 12s ago</span></div>
      <div class="stkh" data-k="plan"><div class="pstyle${o.bars ? ' bars' : ''}"><div class="rings">${pl.rings}</div><div class="barsv">${pl.bars}</div></div>
      <div class="paused"><span class="ptile">${sym('locslash')}</span><span class="col"><b>Usage paused</b><span>Waiting to confirm you’re in ${FLAG.CA} Canada</span></span></div>
      <div class="paused"><span class="ptile">${sym('wifislash')}</span><span class="col"><b>Usage paused</b><span>Waiting for a stable connection to Anthropic</span></span></div></div></div>`,
    keepawake: `<div class="pv-ka"><span class="bc" data-beacon></span><span class="col"><span class="t" data-k="kat">Holding awake · lid closed</span><span class="s sub" data-k="kas">Agents keep running even after you close the lid.</span></span><span class="seg" data-k="seg"><i class="th"></i><i data-m="0">${sym('moonzzz')}</i><i data-m="1">${sym('laptop')}</i><i data-m="2" class="on">${sym('laptopdown')}</i></span></div>`,
  };
  return `<div class="pv${o.compact ? ' compact' : ''}${o.cls ? ' ' + o.cls : ''}">
    <svg class="pv-arrow" viewBox="0 0 26 11" aria-hidden="true"><path d="M0 11C6.5 11 9.2 1.2 13 1.2S19.5 11 26 11z"/><path class="e" d="M0 11C6.5 11 9.2 1.2 13 1.2S19.5 11 26 11"/></svg>
    <div class="pv-body">
      <div class="pv-hd" data-k="hd" data-in><span class="rd" data-k="hdr"></span><span class="tx">
        <span class="stk t" data-k="hdt"><span>Protected</span><span class="am">Blocking Claude</span><span class="am">Blocking — connection unstable</span></span>
        <span class="stk s" data-k="hds"><span><i class="dot"></i>Fenced to ${FLAG.CA} Canada · path open</span><span>Outside Canada — Claude is held, not failed</span><span>No usable path — requests held, resume on their own</span></span></span>
        <i class="sw on"></i></div>
      <div class="mid">${order.map((k, i) => `<div class="sec${on(k)}" data-sec="${k}" data-in><div>${i && k !== 'net' ? '<hr>' : ''}${sec[k]}</div></div>`).join('')}</div>
      <hr class="full">
      <div class="pv-ft" data-in><span class="pl">${sym('macwin')}Open Dashboard<span class="k">⌘D</span></span><span class="ic">${sym('gear')}</span><span class="ic">${sym('term')}</span><span class="ic">${sym('power')}</span></div>
    </div></div>`;
}
TW.popoverHTML = popoverHTML;
/* wire a built popover: marks, refs, natural heights */
function wirePopover(root, o = {}) {
  const p = { root, k: {}, slots: {}, H: {} };
  $$('[data-k]', root).forEach(e => p.k[e.dataset.k] = e);
  $$('[data-slot]', root).forEach(e => p.slots[e.dataset.slot] = e);
  p.state = 'clear';
  TW.radar(p.k.hdr, () => ({ state: p.state }), { k: o.k });
  $$('[data-mark]', root).forEach(e => TW.model(e, e.dataset.mark, true, { k: o.k }));
  TW.beacon($('[data-beacon]', root), () => ({ mode: p.awake ?? 2 }), { k: o.k });
  p.measure = () => {
    for (const [n, s] of Object.entries(p.slots)) p.H[n] = s.firstElementChild.offsetHeight;
    $$('.stkh', root).forEach(s => s.__h = [...s.children].map(c => c.offsetHeight));
  };
  return p;
}
TW.wirePopover = wirePopover;
/* a popover at rest: every stack on its first variant, nobody waiting */
function restPopover(p) {
  $$('[data-slot="ny"]', p.root).forEach(s => s.style.display = 'none');
  p.k.hand.style.display = 'none';
  p.measure();
  $$('.stk, .stkh', p.root).forEach(s => stackTo(s, [1, 0, 0]));
}
TW.restPopover = restPopover;
/* weights → a stack of variants: opacities and the container's height */
function stackTo(s, w) {
  const sum = w.reduce((a, b) => a + Math.max(0, b), 0) || 1;
  [...s.children].forEach((c, i) => { const v = clamp(Math.max(0, w[i] || 0) / sum); c.style.opacity = v.toFixed(3); c.style.visibility = v < .01 ? 'hidden' : ''; c.style.zIndex = v > .5 ? 1 : 0; });
  if (s.__h) s.style.height = s.__h.reduce((a, h, i) => a + h * clamp(Math.max(0, w[i] || 0) / sum, 0, 1.1), 0).toFixed(2) + 'px';
}
TW.stackTo = stackTo;

/* the menu bar, Tower's item at its centre */
function menubarHTML(o = {}) {
  return `<div class="mb${o.cls ? ' ' + o.cls : ''}"><span class="app">Terminal</span><span class="mi">Shell</span><span class="mi">Edit</span><span class="mi">View</span><span class="mi">Window</span><span class="mi">Help</span><span class="sp"></span>
    <span class="si tw" data-k="mbtw"><span class="rd" data-k="mbr"></span><span class="np" data-k="mbnp">1</span><span class="ring">${ringSVG(.47)}</span><span class="pct">47%</span></span>
    <span class="si">${sym('stack')}</span><span class="si">${sym('wifi')}</span><span class="si"><svg class="sf" viewBox="0 0 28 14" style="width:25px;height:12px"><rect x=".75" y=".75" width="23" height="12.5" rx="3.6" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="1.2"/><rect x="2.6" y="2.6" width="16" height="8.8" rx="2" fill="currentColor"/><path d="M25.4 5v4" stroke="currentColor" stroke-opacity=".45" stroke-width="1.6" stroke-linecap="round"/></svg></span><span class="si">${sym('slider')}</span><span class="clock" data-k="mbc">${o.clock || 'Tue 9:41'}</span></div>`;
}
TW.menubarHTML = menubarHTML;

/* ══════════════════════════ the director ══════════════════════════
   A scene is a frame of named values, computed from time; apply() paints it. */
function heroScript(t) {
  const f = { t };
  if (REDUCE) { f.open = 1; f.hi = 1; f.sec = [1, 1, 1, 1, 1, 1, 1, 1, 1]; f.ring = [1, 1, 1]; f.ny = 0; f.geo = 0; f.net = 0; f.state = 'clear'; f.step = 0; f.co = 1; return f; }
  f.open = spring(t - .45, .6, .78); f.hi = clamp(spring(t - .2, .35, 1));
  f.sec = [...Array(9)].map((_, i) => spring(t - .75 - i * .07, .6, .82));
  f.ring = [0, 1, 2].map(i => spring(t - 1.25 - i * .14, 1.2, .9));
  f.co = t;
  const S = 3, PER = 19; let u = -1, n = 0; if (t > S) { u = (t - S) % PER; n = Math.floor((t - S) / PER); }
  f.ny = u < 0 ? 0 : win(u, 4, 9.5, .5, .8); f.nyGlow = u < 4 ? 0 : 1 - eo(u - 4.9, .5); f.nyAge = u - 4 + 2.5;   /* PERM_SETTLE_S: a request counts once it has stood */
  const h = u < 0 ? 0 : clamp(win(u, 11.5, 15.6, .45, .95)), kind = n % 2 ? 'net' : 'geo';
  f.geo = kind === 'geo' ? h : 0; f.net = kind === 'net' ? h : 0;
  f.state = h > .5 ? (kind === 'geo' ? 'holdGeo' : 'holdNet') : 'clear';
  f.step = Math.floor(t / 2);
  return f;
}
function ogScript(t) {
  const f = { t };
  const close = 1 - eo(t - 10.85, .42);
  f.open = spring(t - .3, .6, .78) * close; f.hi = clamp(spring(t - .1, .35, 1)) * (1 - eo(t - 11.1, .3));
  f.sec = [...Array(9)].map((_, i) => spring(t - .55 - i * .06, .6, .82));
  f.ring = [0, 1, 2].map(i => spring(t - 1.0 - i * .14, 1.1, .9));
  f.ny = win(t, 2.4, 5.1, .5, .8); f.nyGlow = t < 2.4 ? 0 : 1 - eo(t - 3.3, .5); f.nyAge = t - 2.4 + 2.5;
  f.geo = clamp(win(t, 5.75, 7.75, .45, .95)); f.net = clamp(win(t, 8.25, 10.25, .45, .95));
  f.state = f.geo > .5 ? 'holdGeo' : f.net > .5 ? 'holdNet' : 'clear';
  f.step = Math.floor(t / 2);
  return f;
}
TW.heroScript = heroScript; TW.ogScript = ogScript;
const ms = s => ({ int: Math.round(11 + 3 * Math.sin(s * 1.7) + 2 * Math.sin(s * 3.1)), api: Math.round(214 + 18 * Math.sin(s * 1.3) + 9 * Math.sin(s * 2.9)) });
TW.ms = ms;
const mixc = (a, b, k) => `rgba(${a.map((v, i) => Math.round(lerp(v, b[i], k))).join(',')})`;
function applyScene(sc, f, clockNow) {
  const p = sc.pv, k = p.k, open = f.open;
  /* the popover drops from its status item */
  p.root.style.opacity = clamp(open * 1.8).toFixed(3);
  p.root.style.transform = `translateY(${((1 - open) * -12).toFixed(2)}px) scale(${(.93 + .07 * open).toFixed(4)})`;
  p.root.style.visibility = open < .005 ? 'hidden' : '';
  sc.ins.forEach((e, i) => { const v = f.sec[Math.min(i, f.sec.length - 1)]; e.style.opacity = clamp(v * 1.3).toFixed(3); e.style.transform = `translateY(${((1 - v) * 7).toFixed(2)}px)`; });
  if (sc.mb) { sc.mb.tw.style.background = `rgba(255,255,255,${(.2 * f.hi).toFixed(3)})`; sc.mb.tw.style.boxShadow = `inset 0 0 0 .5px rgba(255,255,255,${(.1 * f.hi).toFixed(3)})`; }
  /* the guard: one state for the radar, a crossfade for the words */
  const h = Math.max(f.geo, f.net);
  p.state = f.state; if (sc.mb) sc.mb.state = f.state;
  k.hd.style.background = mixc([255, 255, 255, .045], [255, 159, 10, .12], h);
  stackTo(k.hdt, [1 - h, f.geo, f.net]); stackTo(k.hds, [1 - h, f.geo, f.net]);
  stackTo(k.net, [1 - f.net, f.net]);
  stackTo(k.loc, [1 - h, f.geo, f.net]);
  stackTo(k.plan, [1 - h, f.geo, f.net]);
  const m = ms(f.step); setText(k.int, String(m.int)); setText(k.api, String(m.api));
  /* the rings sweep in, counting */
  sc.rings.forEach((r, i) => { const v = f.ring[i]; setRing(r.arc, r.p / 100 * v); setText(r.n, String(Math.round(r.p * clamp(v)))); });
  /* needs you: the approval rises to the top, the badge pops */
  const ny = f.ny, nyc = clamp(ny, 0, 1.06);
  p.slots.ny.style.height = (p.H.ny * nyc).toFixed(2) + 'px'; p.slots.ny.style.opacity = clamp(ny * 1.4).toFixed(3);
  p.slots.ny.firstElementChild.style.transform = `translateY(${((1 - clamp(ny)) * -6).toFixed(2)}px) scale(${(.97 + .03 * clamp(ny)).toFixed(4)})`;
  p.slots.ny.firstElementChild.style.background = `rgba(255,159,10,${(.12 * clamp(f.nyGlow || 0)).toFixed(3)})`;
  const lw = clamp(1 - ny, 0, 1.04);
  p.slots.ledger.style.height = (p.H.ledger * lw).toFixed(2) + 'px'; p.slots.ledger.style.opacity = clamp(lw * 1.4 - .2).toFixed(3);
  k.hand.style.opacity = clamp(ny).toFixed(3); k.hand.style.maxWidth = (clamp(ny, 0, 1) * 30).toFixed(1) + 'px';
  setText(k.nwork, ny > .5 ? '2' : '3');
  setText($('.ago', p.slots.ny), ago(Math.max(0, f.nyAge || 0)));
  if (sc.mb) { const s = clamp(spring((f.nyT ?? 0), .35, .6)); sc.mb.np.style.display = ny > .02 ? 'inline-flex' : 'none'; sc.mb.np.style.transform = `scale(${clamp(ny, 0, 1.15).toFixed(3)})`; sc.mb.np.style.opacity = clamp(ny * 1.5).toFixed(3); sc.mb.np.style.marginRight = (2 * clamp(ny)).toFixed(2) + 'px'; }
  /* clocks */
  if (clockNow != null) {
    $$('[data-turn]', p.root).forEach(e => setText(e, elapsed(+e.dataset.turn + clockNow)));
    $$('[data-since]', p.root).forEach(e => setText(e, elapsed(+e.dataset.since + clockNow)));
    setText(k.planh, D.cost + ' today · ' + ago(12 + (clockNow % 48)) + ' ago');
  }
  /* the shimmer and spinner, as functions of time too */
  if (sc.og) {
    $$('.shim', p.root).forEach(e => { e.style.animationDelay = (-(f.t % 1.8)).toFixed(3) + 's'; });
    $$('.spin', p.root).forEach(e => { e.style.animationDelay = (-(f.t % .8)).toFixed(3) + 's'; });
    $$('.wv path', p.root).forEach(e => { e.style.animationDelay = (-(f.t % 1.2) + (+e.style.getPropertyValue('--i')) * .12).toFixed(3) + 's'; });
  }
  if (sc.extra) sc.extra(f);
}
TW.applyScene = applyScene;
function buildScene(host, o = {}) {
  host.insertAdjacentHTML('beforeend', (o.mb !== false ? menubarHTML({ clock: o.clock }) : '') + popoverHTML({ ...o, cls: ((o.cls || '') + ' dyn').trim() }));
  const root = $('.pv', host), pv = wirePopover(root, o);
  const sc = { host, pv, og: !!o.og, ins: [$('.pv-hd', root), ...$$('.mid > .sec:not(.off)', root), $('.pv-ft', root)] };
  if (o.mb !== false) {
    const mb = $('.mb', host); sc.mb = { el: mb, tw: $('[data-k="mbtw"]', mb), np: $('[data-k="mbnp"]', mb), state: 'clear' };
    TW.radar($('[data-k="mbr"]', mb), () => ({ state: sc.mb.state }), { k: o.k });
  }
  sc.rings = $$('.rings .ringc', root).map(r => ({ p: +r.dataset.pct, arc: $('.arc', r), n: $('.n', r) }));
  return sc;
}
TW.buildScene = buildScene;

if (OG) return;          /* og.html drives its own scene from here */

/* ══════════════════════════ the page ══════════════════════════ */
hydrateSymbols();
if (!window.TUI_FRAMES && $('#tuiData')) try { window.TUI_FRAMES = JSON.parse($('#tuiData').textContent); if (!window.TUI_FRAMES.regular) window.TUI_FRAMES = null; } catch (e) {}
const T = s => (window.TW_T || {})[s] || s;   /* page-copy strings from the edition */

/* the reveal: each block rises once */
const rv = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); rv.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' });
$$('.rv').forEach(e => rv.observe(e));
$$('[data-radar]').forEach(e => TW.radar(e, e.dataset.radar, { awake: +(e.dataset.awake || 0), still: e.hasAttribute('data-still') }));
$$('[data-mark]:not(.pv [data-mark])').forEach(e => TW.model(e, e.dataset.mark, !e.hasAttribute('data-still')));

/* ── 01 · the opening: the desk ── */
{
  const fit = $('#deskFit'), desk = $('#desk');
  if (desk) {
    const tpl = $('#callouts');
    desk.insertAdjacentHTML('beforeend', `<div class="wall"><div class="grain"></div></div><div class="win bg" id="bgTerm"><div class="tb"><span class="lights dim"><i></i><i></i><i></i></span><span class="ttl">tower — 132×36</span></div><div class="tgrid" id="bgGrid"></div></div>`);
    const stageHost = el('div', 'stagehost'); desk.appendChild(stageHost);
    const clock = new Date().toLocaleString('en-US', { weekday: 'short' }) + ' ' + new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).replace(/\s?[AP]M/, '');
    const sc = buildScene(stageHost, { clock });
    const pvEl = sc.pv.root;
    const leads = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); leads.setAttribute('class', 'leads'); desk.appendChild(leads);
    if (tpl) desk.appendChild(tpl.content.cloneNode(true));
    hydrateSymbols(desk);
    const cos = $$('.co', desk);
    let mode = '', W = 1200, H = 720, cut = 0;
    const layout = () => {
      const cw = fit.parentElement.clientWidth, wide = cw >= 980;
      mode = wide ? 'wide' : 'narrow';
      desk.classList.toggle('narrow', !wide);
      W = wide ? 1200 : 460; H = wide ? 724 : 640;
      const k = Math.min(1, cw / W);
      desk.style.width = W + 'px'; desk.style.height = H + 'px'; desk.style.transform = `scale(${k})`;
      fit.style.width = (W * k) + 'px'; fit.style.height = (H * k) + 'px';
      const px = W / 2 - 180; pvEl.style.left = px + 'px'; pvEl.style.top = '40px';
      const tw = sc.mb.tw; tw.style.position = 'absolute'; tw.style.left = (W / 2 - tw.offsetWidth / 2) + 'px'; pvEl.style.setProperty('--ax', '180px');
      sc.pv.measure();
      placeCallouts();
    };
    function placeCallouts() {
      leads.innerHTML = '';
      if (mode !== 'wide') { cos.forEach(c => c.style.display = 'none'); return; }
      const pr = { x: parseFloat(pvEl.style.left), y: 40 };
      const anchor = n => { const a = n === 'int' || n === 'api' ? sc.pv.k.net : n === 'hd' ? sc.pv.k.hd : n === 'agents' ? sc.pv.slots.pipe : n === 'agents2' ? sc.pv.slots.infra : $(`[data-sec="${n}"]`, pvEl); let y = 0, e = a; while (e && e !== pvEl) { y += e.offsetTop; e = e.offsetParent; } return pr.y + y + Math.min(a.offsetHeight, 44) / 2 + (n === 'agents' ? 0 : 0); };
      const sides = { l: [], r: [] };
      cos.forEach(c => { c.style.display = ''; sides[c.dataset.side].push(c); });
      for (const [s, list] of Object.entries(sides)) {
        let floor = 48;
        list.forEach(c => {
          const ay = anchor(c.dataset.to), h = c.offsetHeight, y = Math.max(floor, ay - h / 2);
          floor = y + h + 14;
          const x = s === 'l' ? 36 : W - 36 - 250; c.style.left = x + 'px'; c.style.top = y + 'px';
          const x0 = s === 'l' ? x + 250 : x, x1 = s === 'l' ? pr.x + 10 : pr.x + 350, y0 = y + h / 2, mx = (x0 + x1) / 2;
          const d = `M${x0} ${y0} C${mx} ${y0} ${mx} ${ay} ${x1} ${ay}`;
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', d); leads.appendChild(path);
          const len = path.getTotalLength(); path.style.setProperty('--len', len);
          const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle'); dot.setAttribute('cx', x1); dot.setAttribute('cy', ay); dot.setAttribute('r', 2.6); leads.appendChild(dot);
          const halo = document.createElementNS('http://www.w3.org/2000/svg', 'circle'); halo.setAttribute('class', 'halo'); halo.setAttribute('cx', x1); halo.setAttribute('cy', ay); halo.setAttribute('r', 6); leads.appendChild(halo);
          c.__lead = [path, dot, halo];
        });
      }
    }
    /* the terminal behind the glass */
    const TUI = window.TUI_FRAMES;
    if (TUI) tuiDOM($('#bgGrid'), TUI.regular);
    /* callout variants follow the scene */
    const vset = (c, w) => { const vs = $$('.cv', c); vs.forEach((v, i) => { const x = clamp(w[i] ?? 0); v.style.opacity = x.toFixed(3); v.style.visibility = x < .01 ? 'hidden' : ''; }); };
    sc.extra = f => {
      const h = Math.max(f.geo, f.net), m = ms(f.step);
      cos.forEach((c, i) => {
        const to = c.dataset.to;
        if (to === 'hd') vset(c, [1 - h, f.geo, f.net]); else if (to === 'int' || to === 'api') vset(c, [1 - f.net, f.net]); else if (to === 'location') vset(c, [1 - h, f.geo, f.net]); else vset(c, [1]);
        const shown = REDUCE || f.co > 1.9 + i * .11;
        if (shown && !c.classList.contains('in')) { c.classList.add('in'); c.__lead?.forEach(x => x.classList.add('in')); }
      });
      $$('[data-live="int"]', desk).forEach(e => setText(e, String(m.int)));
      $$('[data-live="api"]', desk).forEach(e => setText(e, String(m.api)));
    };
    layout(); document.fonts?.ready.then(layout); addEventListener('resize', layout);
    let start = null;
    TW.ticker(desk, P => { if (start == null) start = P; applyScene(sc, heroScript(P - start), now() - T0); return true; });
    applyScene(sc, heroScript(0), 0);
  }
}

/* ── the terminal frames, composed by the real src/tower-tui.py ── */
function tuiDOM(box, F, opt = {}) {
  const H = opt.rows || F.h, W = F.w, clock = new Date().toTimeString().slice(0, 5);
  const rows = Array.from({ length: H }, () => Array(W).fill(null));
  F.ops.forEach((o, n) => {
    let [y, x, t, p, st, fx] = o; if (y >= H) return;
    if (/^\d\d:\d\d$/.test(t) && y <= 2) t = clock;
    const cls = 'p' + (p || 1) + (st & 1 ? ' b' : '') + (st & 2 ? ' dm' : '') + (fx && fx[0] === 'shim' && !REDUCE ? ' sh' : '');
    const key = fx && fx[0] === 'spin' ? 's' + n : cls;
    [...t].forEach((ch, k) => { const X = x + k; if (X >= 0 && X < W) rows[y][X] = { ch, cls, key, fx }; });
  });
  const spins = []; box.innerHTML = '';
  rows.forEach(cells => {
    const l = el('span', 'l'); let run = null, txt = '', gap = '';
    const flush = () => { if (!run) return; const sp = el('span', run.cls); sp.textContent = txt; if (run.fx && run.fx[0] === 'spin') spins.push([sp, run.fx[1]]); l.appendChild(sp); run = null; txt = ''; };
    cells.forEach(c => { if (!c) { flush(); gap += ' '; return; } if (gap) { l.appendChild(document.createTextNode(gap)); gap = ''; } if (!run || run.key !== c.key) { flush(); run = c; } txt += c.ch; });
    flush(); box.appendChild(l);
  });
  return spins;
}
TW.tuiDOM = tuiDOM;

/* ── 02 · at a glance: weather tiles are HTML; nothing to wire but marks ── */

/* ── 03 · agents: the needs-you queue, entering in rank ── */
{
  const host = $('#queue');
  if (host) {
    host.innerHTML = `<div class="pv-ah"><span class="pv-cap">AGENTS</span><span class="cnt"><span class="hand" style="max-width:none">${sym('hand')}2</span><span>${wave()}3</span><span>${sym('turn')}1</span><span class="dn">${sym('checkf')}41</span></span></div>`
      + nyHTML(AG.ledger, 'pending_tool', 'waiting for approval · ' + AG.ledger.title, '1m')
      + nyHTML({ name: 'ios-app', meta: 'Sonnet 5.5 · Medium' }, 'asking', 'asked you a question · Offline drafts', '4m')
      + nyHTML({ name: 'docs-site', meta: 'Haiku 5.5 · Low' }, 'done', 'done — your turn · rewrote 14 pages for the v3 API, links check clean', '1m')
      + rowHTML(AG.pipe, 'pipe') + rowHTML(AG.checkout, 'checkout') + rowHTML(AG.infra, 'infra')
      + `<div class="pv-rest">${sym('chev')}<span>Resting · 2</span></div>`;
    $$('[data-mark]', host).forEach(e => TW.model(e, e.dataset.mark, true));
    const rows = [...host.children];
    rows.forEach(r => r.style.opacity = 0);
    const io = new IntersectionObserver(es => { if (!es[0].isIntersecting) return; io.disconnect();
      rows.forEach((r, i) => setTimeout(() => { r.style.opacity = ''; r.classList.add('enter'); if (r.dataset.ny === 'done') r.classList.add('drawn'); }, REDUCE ? 0 : 120 + i * 70)); }, { threshold: .35 });
    io.observe(host);
    TW.ticker(host, () => { $$('[data-turn]', host).forEach(e => setText(e, elapsed(+e.dataset.turn + now() - T0))); $$('[data-since]', host).forEach(e => setText(e, elapsed(+e.dataset.since + now() - T0))); return false; });
    setInterval(() => { if (!document.hidden) { $$('[data-turn]', host).forEach(e => setText(e, elapsed(+e.dataset.turn + now() - T0))); $$('[data-since]', host).forEach(e => setText(e, elapsed(+e.dataset.since + now() - T0))); } }, 1000);
  }
  const badge = $('#badgeDemo');
  if (badge) {
    badge.innerHTML = `<div class="mb mini"><span class="si tw on"><span class="rd" data-radar="clear"></span><span class="np on">2</span><span class="ring">${ringSVG(.47)}</span><span class="pct">47%</span></span></div>`;
    $$('[data-radar]', badge).forEach(e => TW.radar(e, 'clear'));
  }
}

/* ── 04 · make it yours: Settings → Popover, live ── */
{
  const host = $('#custom');
  if (host) {
    const pvHost = $('#customPv'), list = $('#customList');
    pvHost.innerHTML = popoverHTML({ show: ['net', 'agents', 'location', 'plan', 'keepawake'], cls: 'still' });
    const root = $('.pv', pvHost), pv = wirePopover(root);
    restPopover(pv);
    const ROWS = [['net', 'wifi', 'Network weather'], ['agents', 'radio', 'Agents'], ['location', 'locline', 'Location'], ['apps', 'macwin', 'Claude apps'], ['plan', 'gauge', 'Plan usage'], ['keepawake', 'cup', 'Keep awake']];
    const state = { net: 1, agents: 1, location: 1, apps: 0, plan: 1, keepawake: 1, bars: 0, compact: 0 };
    list.innerHTML = `<div class="sgroup">${ROWS.map(([k, s, t]) => `<div class="srow${state[k] ? '' : ' dim'}" data-key="${k}"><span class="hdl">${sym('handle')}</span><span class="si2">${sym(s)}</span><span class="sl">${t}</span><button type="button" class="sw${state[k] ? ' on' : ''}" role="switch" aria-checked="${!!state[k]}" aria-label="${t}"></button></div>`).join('')}</div>
      <div class="sgroup"><div class="srow"><span class="sl">Plan usage style</span><span class="segt" data-key="bars"><button type="button" data-v="0" class="on">Rings</button><button type="button" data-v="1">Bars</button></span></div>
      <div class="srow"><span class="sl">Density</span><span class="segt" data-key="compact"><button type="button" data-v="0" class="on">Comfortable</button><button type="button" data-v="1">Compact</button></span></div></div>`;
    const apply = () => {
      ROWS.forEach(([k]) => { $(`[data-sec="${k}"]`, root).classList.toggle('off', !state[k]); const r = $(`.srow[data-key="${k}"]`, list); r.classList.toggle('dim', !state[k]); const sw = $('.sw', r); sw.classList.toggle('on', !!state[k]); sw.setAttribute('aria-checked', !!state[k]); });
      const first = $$('.mid > .sec:not(.off)', root)[0]; $$('.mid > .sec', root).forEach(s => s.classList.toggle('lead', s === first));
      $('.pstyle', root).classList.toggle('bars', !!state.bars);
      root.classList.toggle('compact', !!state.compact);
      $$('.segt', list).forEach(sg => $$('button', sg).forEach(b => b.classList.toggle('on', +b.dataset.v === state[sg.dataset.key])));
      requestAnimationFrame(() => { $$('.stkh', root).forEach(s => { s.__h = [...s.children].map(c => c.offsetHeight); stackTo(s, [1, 0, 0]); }); });
    };
    let user = false;
    list.addEventListener('click', e => {
      const sw = e.target.closest('.sw'), sb = e.target.closest('.segt button');
      if (sw) { const k = sw.closest('.srow').dataset.key; state[k] = state[k] ? 0 : 1; user = true; apply(); }
      if (sb) { state[sb.parentElement.dataset.key] = +sb.dataset.v; user = true; apply(); }
    });
    apply();
    /* once, when it is first seen: compose it the way the screenshots do */
    const steps = [() => { state.apps = 1; }, () => { state.bars = 1; }, () => { state.compact = 1; }, () => { state.net = 0; }, () => { state.net = 1; state.compact = 0; }, () => { state.bars = 0; state.apps = 0; }];
    const io = new IntersectionObserver(es => { if (!es[0].isIntersecting || REDUCE) return; io.disconnect();
      steps.forEach((s, i) => setTimeout(() => { if (!user) { s(); apply(); } }, 1100 + i * 1700)); }, { threshold: .5 });
    io.observe(host);
  }
}

/* ── 05 · the proxy: requests flowing, held, resuming ── */
{
  const flow = $('#flow');
  if (flow) {
    const wire = $('.wire', flow), A = $('#nCode', flow), G = $('#nGate', flow), B = $('#nApi', flow);
    const btns = $$('.chipbtn', flow);
    let mode = 'pass', userPick = false, lastSwitch = 0;
    const gateR = $('#gateRadar', flow); TW.radar(gateR, () => ({ state: mode === 'pass' ? 'clear' : mode === 'geo' ? 'holdGeo' : 'holdNet' }));
    const setMode = m => {
      mode = m; flow.classList.toggle('held', m !== 'pass');
      btns.forEach(b => b.classList.toggle('on', b.dataset.m === m));
      $('#ckGeo', flow).classList.toggle('bad', m === 'geo'); $('#ckNet', flow).classList.toggle('bad', m === 'net');
      $$('[data-when]', flow).forEach(e => e.style.display = e.dataset.when.split(' ').includes(m) ? '' : 'none');
    };
    btns.forEach(b => b.onclick = () => { userPick = true; setMode(b.dataset.m); });
    setMode('pass');
    let geo = null;
    const measure = () => {
      const fr = flow.getBoundingClientRect(), c = e => { const r = e.getBoundingClientRect(); return { x: r.left - fr.left, y: r.top - fr.top, w: r.width, h: r.height }; };
      const a = c(A), g = c(G), b = c(B), stacked = Math.abs(a.y - g.y) > 40;
      wire.setAttribute('viewBox', `0 0 ${fr.width} ${fr.height}`);
      const p1 = stacked ? [[a.x + a.w / 2, a.y + a.h], [g.x + g.w / 2, g.y]] : [[a.x + a.w, a.y + a.h / 2], [g.x, g.y + g.h / 2]];
      const p2 = stacked ? [[g.x + g.w / 2, g.y + g.h], [b.x + b.w / 2, b.y]] : [[g.x + g.w, g.y + g.h / 2], [b.x, b.y + b.h / 2]];
      geo = { p1, p2 };
      $$('.base', wire).forEach((l, i) => { const p = i ? p2 : p1; l.setAttribute('d', `M${p[0][0]} ${p[0][1]}L${p[1][0]} ${p[1][1]}`); });
    };
    wire.innerHTML = '<path class="base"/><path class="base"/>';
    measure(); addEventListener('resize', measure); document.fonts?.ready.then(measure);
    const pk = []; let lastSpawn = 0;
    const at = (seg, k) => [lerp(seg[0][0], seg[1][0], k), lerp(seg[0][1], seg[1][1], k)];
    TW.ticker(flow, P => {
      if (!geo) return true;
      if (!userPick && !REDUCE) { const u = P % 15; const m = u < 6 ? 'pass' : u < 10 ? 'geo' : u < 11.5 ? 'pass' : 'net'; if (u >= 14) { if (mode !== 'pass') setMode('pass'); } else if (m !== mode) setMode(m); }
      if (P - lastSpawn > .42) { lastSpawn = P; const n = document.createElementNS('http://www.w3.org/2000/svg', 'circle'); n.setAttribute('r', 3.2); n.setAttribute('class', 'pk'); wire.appendChild(n); pk.push({ n, s: 0, k: 0, v: .55 + Math.random() * .25, q: 0 }); }
      const held = mode !== 'pass';
      for (let i = pk.length - 1; i >= 0; i--) {
        const o = pk[i], dt = 1 / 60;
        if (o.s === 0) { const stopAt = held ? .94 - Math.min(o.q, 8) * .07 : 1; o.k = Math.min(stopAt, o.k + o.v * dt); if (held && o.k >= stopAt - .001) { if (!o.waiting) { o.waiting = 1; o.q = pk.filter(x => x.waiting).length; } } if (!held) { o.waiting = 0; } if (o.k >= 1) { o.s = 1; o.k = 0; } }
        else { o.k += o.v * 1.25 * dt; if (o.k >= 1) { o.n.remove(); pk.splice(i, 1); continue; } }
        const [x, y] = at(o.s ? geo.p2 : geo.p1, o.k);
        o.n.setAttribute('cx', x.toFixed(1)); o.n.setAttribute('cy', y.toFixed(1));
        o.n.classList.toggle('am', !!o.waiting);
        o.n.style.opacity = o.s ? (1 - o.k * .6).toFixed(2) : Math.min(1, o.k * 6).toFixed(2);
      }
      if (pk.length > 40) { const o = pk.shift(); o.n.remove(); }
      return true;
    });
  }
}

/* ── 06 · Claude apps: the toolbar menu, its highlight wandering ── */
{
  const menu = $('#appsMenu');
  if (menu) { const its = $$('.it', menu); let i = 0; setInterval(() => { if (document.hidden) return; its.forEach((x, k) => x.classList.toggle('hl', k === i)); i = (i + 1) % (its.length + 1); }, 1400); }
}

/* ── 07 · usage, location, awake ── */
{
  const big = $('#bigRings');
  if (big) {
    const R = [['Session', D.plan.session], ['Weekly', D.plan.week], ['Fable', D.plan.fable]];
    big.innerHTML = R.map(([l, [p, r]]) => `<div class="ringc" data-pct="${p}"><div class="ring">${ringSVG(0, tint(p))}<span class="n"><b>0</b><small>%</small></span></div><div><div class="l">${l}</div><div class="rs">${sym('refresh')}${r}</div></div></div>`).join('');
    const rs = $$('.ringc', big).map(r => ({ p: +r.dataset.pct, arc: $('.arc', r), n: $('.n b', r) }));
    let s0 = null;
    const io = new IntersectionObserver(es => { if (es[0].isIntersecting && s0 == null) { s0 = performance.now(); io.disconnect(); TW.wake(); } }, { threshold: .4 });
    io.observe(big);
    TW.ticker(big, () => { if (s0 == null) return false; const t = (performance.now() - s0) / 1000; let more = false;
      rs.forEach((r, i) => { const v = REDUCE ? 1 : spring(t - i * .15, 1.2, .9); setRing(r.arc, r.p / 100 * v); setText(r.n, String(Math.round(r.p * clamp(v)))); if (t < 3) more = true; }); return more; });
  }
  const lamp = $('#lamp');
  if (lamp) {
    let mode = 2; const seg = $('.seg', lamp.closest('.card')), titleE = $('#lampT'), lineE = $('#lampL');
    TW.beacon($('.bc', lamp), () => ({ mode }));
    const W = [['Sleep allowed', 'The Mac may sleep on its own — a long agent can be cut off.'], ['Holding awake · lid open', 'Agents keep running; the screen still sleeps.'], ['Holding awake · lid closed', 'Agents keep running even after you close the lid.']];
    const set = m => { mode = m; $$('i[data-m]', seg).forEach(i => i.classList.toggle('on', +i.dataset.m === m)); $('.th', seg).style.transform = `translateX(${m * 30}px)`; setText(titleE, W[m][0]); setText(lineE, W[m][1]); TW.wake(); };
    set(2); let k = 2;
    $$('i[data-m]', seg).forEach(i => i.onclick = () => { auto = false; set(+i.dataset.m); });
    let auto = true; setInterval(() => { if (auto && !document.hidden && !REDUCE) { k = (k + 1) % 3; set(k); } }, 2600);
  }
  $$('.pv .seg').forEach(seg => { const on = $('i.on', seg); if (on) $('.th', seg).style.transform = `translateX(${(+on.dataset.m) * 30}px)`; });
}

/* ── 08 · the dashboard, five pages ── */
{
  const host = $('#dash');
  if (host) {
    host.innerHTML = dashHTML(); hydrateSymbols(host);
    const win = $('.dw', host), fitE = host;
    $$('[data-mark]', win).forEach(e => TW.model(e, e.dataset.mark, !e.hasAttribute('data-still')));
    $$('[data-radar]', win).forEach(e => TW.radar(e, e.dataset.radar));
    const pages = $$('.dpage', win), items = $$('.dside .it', win), lit = $('.dside .lit', win);
    let cur = 0, auto = true;
    const show = (i, anim = true) => {
      cur = i; items.forEach((it, k) => it.classList.toggle('on', k === i)); tabs.forEach((b, k) => b.classList.toggle('on', k === i));
      const it = items[i]; lit.style.transform = `translateY(${it.offsetTop}px)`; lit.style.height = it.offsetHeight + 'px';
      pages.forEach((p, k) => p.classList.toggle('on', k === i));
      const p = pages[i]; setText($('.dtitle b', win), p.dataset.title); setText($('.dtitle span', win), p.dataset.sub);
      $$('.dtb .tb2', win).forEach(b => b.style.display = (b.dataset.on || '').split(' ').includes(p.dataset.key) ? '' : 'none');
    };
    const tabs = $$('.dtabs button', host.closest('section'));
    items.forEach((it, i) => it.onclick = () => { auto = false; show(i); });
    tabs.forEach((b, i) => b.onclick = () => { auto = false; show(i); });
    const layout = () => { const cw = host.clientWidth, k = Math.min(1, cw / 1020); win.style.transform = `scale(${k})`; host.style.height = (660 * k) + 'px'; };
    layout(); addEventListener('resize', layout);
    show(0, false);
    let seenIt = false;
    const io = new IntersectionObserver(es => { seenIt = es[0].isIntersecting; }, { threshold: .4 }); io.observe(host);
    setInterval(() => { if (auto && seenIt && !document.hidden && !REDUCE) show((cur + 1) % pages.length); }, 5200);
    setInterval(() => { if (!document.hidden) $$('[data-turn]', win).forEach(e => setText(e, elapsed(+e.dataset.turn + now() - T0))); }, 1000);
  }
}
function dashHTML() {
  const SEED = (() => { let s = 7; return () => (s = (s * 16807) % 2147483647) / 2147483647; })();
  const hist = [...Array(60)].map((_, i) => ({ i: 9 + 4 * Math.sin(i / 5) + SEED() * 5, a: 186 + 22 * Math.sin(i / 7) + SEED() * 30 }));
  const line = (key, w, h, max, close) => { const pts = hist.map((p, i) => [(i / 59 * w).toFixed(1), (h - p[key] / max * h).toFixed(1)]); return 'M' + pts.map(p => p.join(' ')).join(' L') + (close ? ` L${w} ${h} L0 ${h}Z` : ''); };
  const days = [38.4, 52.1, 47.9, 12.3, 8.6, 61.7, 44.2], dn = [...Array(7)].map((_, k) => k === 6 ? 'Today' : new Date(Date.now() - (6 - k) * 864e5).toLocaleDateString('en-US', { weekday: 'short' }));
  const hosts = ['api.anthropic.com', 'api.anthropic.com', 'statsig.anthropic.com', 'registry.npmjs.org', 'api.anthropic.com', 'github.com', 'api.anthropic.com', 'api.anthropic.com', 'registry.npmjs.org', 'api.anthropic.com', 'statsig.anthropic.com', 'api.anthropic.com'];
  const tm = k => { const d = new Date(Date.now() - k * 5000); return d.toTimeString().slice(0, 8); };
  const agentRow = (a, key) => `<div class="drow"><div class="gl" data-mark="${a.tier}"></div><div class="col"><div class="ln"><span class="nm">${a.name}</span><span class="mm">${a.meta}</span>${a.warn ? `<span class="wn">${sym('warn')}</span>` : ''}<span class="tl">${fmt(a.tools)} tools</span><span class="ck" data-turn="${a.turn}">${elapsed(a.turn)}</span></div><div class="ln"><span class="act">${a.act}</span></div>${a.subs ? treeHTML(a.subs, a.more) : ''}</div></div>`;
  const ring = (p, l, r) => `<div class="dring"><div class="ring">${ringSVG(p / 100)}<span class="n">${p}%</span></div><b>${l}</b><span>resets in ${r}</span></div>`;
  const sw = on => `<i class="sw${on ? ' on' : ''}"></i>`;
  return `<div class="dw">
  <aside class="dside"><span class="lights"><i></i><i></i><i></i></span><i class="lit"></i>
    <div class="it">${sym('grid')}Overview</div><div class="it">${sym('radio')}Agents<em>2</em></div><div class="it">${sym('wifi')}Network</div><div class="it">${sym('gauge')}Usage</div><hr><div class="it">${sym('gear')}Settings</div>
    <div class="dfoot"><span class="rd" data-radar="clear"></span><div><b>Protected</b><span>${FLAG.CA} Toronto, ON</span></div></div></aside>
  <div class="dmain"><div class="dtb"><span class="tbc">${sym('sidebar')}</span><span class="dtitle"><b>Overview</b><span>Protected</span></span><span class="sp"></span>
    <span class="tbc tb2" data-on="overview network">${sym('speed')}</span><span class="tbc tb2" data-on="usage">${sym('refresh')}</span><span class="tbc wide">${sym('macwins')}${sym('chevd', 'sm')}</span><span class="tbc">${sym('term')}</span></div>
  <div class="dpages">
  <section class="dpage" data-key="overview" data-title="Overview" data-sub="Protected">
    <div class="dcard dhero"><span class="rd" data-radar="clear"></span><div class="col"><b>Protected</b><span>Claude is fenced to ${FLAG.CA} Canada, and the path to Anthropic is open.</span><small>${FLAG.CA} ${D.loc.city}<i>·</i>${D.loc.isp}<i>·</i><code>${D.loc.ip}</code></small></div><span class="gd">Guard ${sw(1)}</span></div>
    <div class="dg2"><div class="dcard dagents"><div class="dh">${sym('radio')}<b>Live agents</b><span>3 working · 2 need you</span></div>
      <div class="dny">${sym('hand')}<b>ledger-api</b><span>waiting for approval · Bash: psql -f migrations/0042…</span><em>1m</em></div>
      ${agentRow(AG.pipe)}${agentRow(AG.checkout)}${agentRow(AG.infra)}<div class="drest">${sym('zzz')}2 resting${sym('chev')}</div></div>
      <div class="dcol"><div class="dcard"><div class="dh">${sym('gauge')}<b>Plan usage</b><span>Details</span></div><div class="drings">${ring(34, 'Session', '2h 14m')}${ring(47, 'Weekly', '2d 4h')}${ring(22, 'Fable', '2d 4h')}</div></div>
      <div class="dcard"><div class="dh">${sym('wifi')}<b>Network</b><span>Details</span></div><div class="dok">${sym('wifi')}Connection healthy</div><div class="dnums"><div><span>Internet</span><b>11<small> ms</small></b></div><div><span>API</span><b>214<small> ms</small></b></div></div><svg class="spark" viewBox="0 0 300 50" preserveAspectRatio="none"><path d="${line('a', 300, 50, 400, true)}" class="fa"/><path d="${line('a', 300, 50, 400)}" class="la"/></svg></div>
      <div class="dcard"><div class="dh">${sym('arrows')}<b>Requests</b><span>4,812 passed · 7 held</span></div><div class="dreq">${hosts.slice(0, 4).map((h, k) => `<div><i class="${h.includes('anthropic') ? 'w' : ''}"></i>${h}<em>${tm(k)}</em></div>`).join('')}</div></div></div></div>
  </section>
  <section class="dpage" data-key="agents" data-title="Agents" data-sub="3 working · 2 need you">
    <div class="dag"><div class="dlist"><h6>NEEDS YOU<em>2</em></h6>
      <div class="dli">${sym('hand', 'or')}<div><b>ledger-api <i>Fable 5.1 · Max</i></b><span>waiting for approval</span></div><em>1m</em></div>
      <div class="dli">${sym('qbubble', 'ind')}<div><b>ios-app <i>Sonnet 5.5 · Medium</i></b><span>asked you a question</span></div><em>4m</em></div>
      <h6>WORKING<em>3</em></h6>
      <div class="dli"><span class="gl" data-mark="opus"></span><div><b>data-pipeline <i>Opus 5.5 · High</i></b><span>waiting on 2 subagents…</span></div><em data-turn="2280">38m</em></div>
      <div class="dli on"><span class="gl" data-mark="opus"></span><div><b>checkout-web <i>Opus 5.5 · High</i></b><span>Running pnpm test payments</span></div><em data-turn="1260">21m</em></div>
      <div class="dli"><span class="gl" data-mark="sonnet"></span><div><b>infra <i>Sonnet 5.5 · High</i></b><span>thinking…</span></div><em data-turn="520">8m</em></div>
      <h6>RESTING<em>2</em></h6><div class="dli dim"><span class="gl" data-mark="sonnet" data-still></span><div><b>marketing-site</b><span>resting</span></div><em>1.7h</em></div></div>
    <div class="ddet"><div class="dtop"><span class="gl big" data-mark="opus"></span><div><b>checkout-web <i>Opus 5.5 · High</i></b><span>${sym('gear')} working <i>· for 21m ·</i> ${sym('branch')} <code>feat/partial-refunds</code></span></div></div>
      <span class="wbtn">${sym('term')}Show Terminal</span>
      <div class="dcard dnow">${wave()}<span class="shim">Running pnpm test payments</span></div>
      <div class="dtiles"><div class="dcard">${sym('tools')}<span>Tools</span><b>148</b></div><div class="dcard">${sym('doc')}<span>Files</span><b>9</b></div><div class="dcard">${sym('fan')}<span>Subagents</span><b>3</b></div><div class="dcard">${sym('xcircle')}<span>Errors</span><b>1</b></div></div>
      <div class="dcard"><div class="dh">${sym('bubble')}<b>Asked</b></div><p>add partial refunds to checkout: a line-item picker, the Stripe call, and tests</p></div>
      <div class="dcard"><div class="dh">${sym('info')}<b>Details</b></div><dl><dt>Folder</dt><dd><code>~/code/checkout-web</code></dd><dt>Branch</dt><dd>feat/partial-refunds</dd><dt>Terminal</dt><dd>ttys002</dd><dt>Started</dt><dd>2.6h ago</dd><dt>Guard</dt><dd>through Tower</dd></dl></div></div></div>
  </section>
  <section class="dpage" data-key="network" data-title="Network" data-sub="Connection healthy">
    <div class="dcard dnh"><span class="wtile">${sym('wifi')}</span><div class="col"><b>Connection healthy</b><span>Internet and the Anthropic API are both reachable</span><small>Checked 2s ago</small></div><div class="dbig"><div><span>${sym('globe')}Internet</span><b>11<small>ms</small></b></div><div><span>${sym('rack')}Anthropic API</span><b>214<small>ms</small></b></div></div></div>
    <div class="dg2 n"><div class="dcol"><div class="dcard dlat"><div class="dh">${sym('ecg')}<b>Latency</b><span><i class="k1"></i>Anthropic API<i class="k2"></i>Internet<em>last 10 min</em></span></div>
      <svg viewBox="0 0 520 190" preserveAspectRatio="none" class="lat"><g class="gr"><path d="M0 1H520M0 64H520M0 127H520M0 189H520"/></g><path class="fa" d="${line('a', 520, 190, 300, true)}"/><path class="la" d="${line('a', 520, 190, 300)}"/><path class="li" d="${line('i', 520, 190, 300)}"/></svg></div>
      <div class="dcard dspd"><div class="dh">${sym('speed')}<b>Speed test</b></div><div class="row"><span class="dl">${sym('down')}</span><div><b>412<small> Mbps</small></b><span>Download · 10m ago</span></div><span class="wbtn sm">Run Test</span></div></div></div>
      <div class="dcard dtraf"><div class="dh">${sym('arrows')}<b>Live traffic</b><span>4,812 allowed · 7 blocked</span></div>${hosts.map((h, k) => `<div class="tr${k % 2 ? ' z' : ''}"><i></i><em>${tm(k)}</em>${h}${h === 'api.anthropic.com' ? '<span class="cc">Claude</span>' : ''}</div>`).join('')}</div></div>
  </section>
  <section class="dpage" data-key="usage" data-title="Usage" data-sub="Plan updated 12s ago">
    <div class="dg2 u"><div class="dcard"><div class="dh">${sym('gauge')}<b>Plan limits</b><span>12s ago</span></div>${[['Session', 34, '2h 14m'], ['Weekly', 47, '2d 4h'], ['Fable', 22, '2d 4h']].map(([l, p, r]) => `<div class="pl"><div><b>${l}</b><span>${sym('refresh')}${r}</span><em>${p}%</em></div><i><u style="width:${p}%"></u></i></div>`).join('')}<small>1,840 requests · 9 sessions in the last 24 hours</small></div>
      <div class="dcard"><div class="dh">${sym('dollar')}<b>Cost estimate</b><span>list price · not your plan</span></div><div class="cst"><div><span>Today</span><b class="xl">$44</b><small>18.1M tokens</small></div><div><span>Session</span><b>$18</b></div><div><span>This week</span><b>$265</b><small>on pace for ~$301</small></div></div>
        ${[['Opus', 58.5, '$171'], ['Fable', 19.8, '$61'], ['Sonnet', 17, '$27'], ['Haiku', 4.7, '$5.60']].map(([m, p, c]) => `<div class="mdl"><b>${m}</b><i><u style="width:${p}%"></u></i><em>${Math.round(p)}%</em><strong>${c}</strong></div>`).join('')}</div>
      <div class="dcard"><div class="dh">${sym('bars')}<b>Last 7 days</b><span>$265 in 7 days</span></div><div class="d7">${days.map((c, k) => `<div class="${k === 6 ? 'td' : ''}"><i style="height:${(c / 62 * 100).toFixed(1)}%"></i><span>${dn[k]}</span></div>`).join('')}</div></div>
      <div class="dcard"><div class="dh">${sym('clock')}<b>Where your limits go</b><span class="sgm"><b>24h</b><i>7d</i></span></div>${[['Give "general-purpose" subagents a cheaper model', 62], ['Start fresh when you switch tasks', 41]].map(([t, p]) => `<div class="tip"><div><b>${t}</b><em>${p}%</em></div><i><u style="width:${p}%"></u></i></div>`).join('')}<small>Top: general-purpose 34% · Explore 12%</small></div></div>
  </section>
  <section class="dpage" data-key="settings" data-title="Settings" data-sub="Tower 4.0.0">
    <div class="dset"><h5>Guard</h5><div class="grp"><div><span>Country</span><span class="pick">${FLAG.CA} Canada ${sym('updown')}</span></div><div><span>Enforce<small>Hold Claude while you're outside Canada</small></span>${sw(1)}</div><div><span>Scope</span><span class="pick plain">Claude only ${sym('updown')}</span></div></div>
      <h5>Menu bar</h5><div class="grp"><div><span>Shows</span><span class="pick plain">Week % ${sym('updown')}</span></div><div><span>Needs-you badge<small>Counts failures, approvals and questions — never a finished turn</small></span>${sw(1)}</div><div><span>Highlight</span><span class="pick plain"><i class="yd"></i>60% ${sym('updown')} <i class="rd2"></i>85% ${sym('updown')}</span></div></div>
      <h5>Popover</h5><div class="grp">${[['wifi', 'Network weather', 1], ['radio', 'Agents', 1], ['locline', 'Location', 1], ['macwin', 'Claude apps', 0], ['gauge', 'Plan usage', 1], ['cup', 'Keep awake', 1]].map(([s, t, on]) => `<div class="${on ? '' : 'dim'}"><span>${sym('handle', 'hd')}${sym(s)}${t}</span>${sw(on)}</div>`).join('')}</div></div>
  </section>
  </div></div></div>`;
}

/* ── 09 · the terminal ── */
{
  const stage = $('#tStage');
  const TUI = window.TUI_FRAMES;
  if (stage && TUI) {
    const grid = $('.tgrid', stage), fitE = $('.tfit', stage), size = $('.ttl small', stage);
    const probe = el('span', '', '0'.repeat(100)); probe.style.cssText = 'position:fixed;left:0;top:0;visibility:hidden;font:12px "JetBrains Mono",monospace;white-space:pre'; document.body.appendChild(probe);
    let cw = 7.2, cur = 'regular', spins = [];
    const measure = () => { cw = probe.getBoundingClientRect().width / 100 || 7.2; };
    const layout = (paint) => {
      const Fr = TUI[cur], W = Math.ceil(Fr.w * cw) + 28, H = Fr.h * 16 + 24;
      const avail = stage.parentElement.clientWidth, k = Math.min(1, avail / W);
      grid.style.width = W + 'px'; grid.style.transform = `scale(${k})`; fitE.style.width = (W * k) + 'px'; fitE.style.height = (H * k) + 'px';
      stage.style.width = (W * k) + 'px';
      setText(size, Fr.w + '×' + Fr.h);
      if (paint) spins = tuiDOM(grid, Fr);
    };
    measure(); layout(true); document.fonts?.ready.then(() => { measure(); layout(true); }); addEventListener('resize', () => layout(false));
    const seg = $('#tSeg'), lit = $('.lit', seg);
    const pick = (b, anim) => { $$('button', seg).forEach(x => x.classList.toggle('on', x === b)); if (!anim) lit.style.transition = 'none'; lit.style.width = b.offsetWidth + 'px'; lit.style.transform = `translateX(${b.offsetLeft - 4}px)`; if (!anim) { void lit.offsetWidth; lit.style.transition = ''; } };
    $$('button', seg).forEach(b => b.onclick = () => { pick(b, true); cur = b.dataset.k; grid.classList.add('out'); setTimeout(() => { layout(true); grid.classList.remove('out'); }, REDUCE ? 0 : 220); });
    requestAnimationFrame(() => pick($('button.on', seg), false)); document.fonts?.ready.then(() => pick($('button.on', seg), false));
    addEventListener('resize', () => pick($('button.on', seg), false));
    setInterval(() => { if (document.hidden) return; const n = Math.floor(Date.now() / 200); spins.forEach(([sp, fr]) => setText(sp, fr[n % fr.length])); }, 200);
  }
  const wt = $('#winTui'); if (wt && TUI) tuiDOM(wt, TUI.compact);
  const mp = $('#macThumb'); if (mp) { mp.innerHTML = popoverHTML({ cls: 'still' }); restPopover(wirePopover($('.pv', mp))); }
}

/* ── 10 · faster: one second of Tower, then and now ──
   Two dot fields of the same 16,036 transcripts. 3.1 sweeps every one of
   them each second; 4.0 lets its own 15,751 probes go, and lights only a
   file that grew. Under each, the daemon's CPU over the last five seconds.
   Every frame is a function of time; nothing runs off screen. */
{
  const fig = $('#scan');
  if (fig) {
    const COLS = 196, ROWS = 82, N = 16036, NREAL = 285, SPAN = 5, RATE = 30;
    let seed = 20261028; const rnd = () => (seed = seed * 16807 % 2147483647) / 2147483647;
    const real = new Uint8Array(N), wave = new Float32Array(N);
    { const ix = Array.from({ length: N }, (_, i) => i); for (let i = N - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [ix[i], ix[j]] = [ix[j], ix[i]]; } for (let i = 0; i < NREAL; i++) real[ix[i]] = 1; }
    for (let i = 0; i < N; i++) wave[i] = .62 * ((i % COLS) / COLS) + .38 * rnd();
    const reals = []; for (let i = 0; i < N; i++) if (real[i]) reals.push(i);
    const h = i => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
    /* a file grows now and then: a fixed, seamless schedule */
    const pings = []; for (let t = 2.6, k = 0; t < 600; k++) { pings.push({ t, i: reals[Math.floor(h(k + 9) * NREAL)] }); t += .35 + 1.3 * h(k); }
    const sides = $$('.sd', fig).map(sd => ({ dots: $('.sc-dots', sd), cpu: $('.sc-cpu canvas', sd), n: $('.sc-ro .n', sd), after: sd.classList.contains('v4') }));
    let W = 0, H = 0, dpr = 1, sx = 1, sy = 1, dd = 1, L = {};
    const at = i => [((i % COLS) + .5) * sx, (Math.floor(i / COLS) + .5) * sy];
    const layer = (aProbe, aReal) => {
      const o = document.createElement('canvas'); o.width = W * dpr; o.height = H * dpr;
      const g = o.getContext('2d'); g.scale(dpr, dpr);
      for (const [want, a, r] of [[0, aProbe, dd], [1, aReal, dd * 1.6]]) {
        if (!a) continue; g.fillStyle = `rgba(255,255,255,${a})`;
        for (let i = 0; i < N; i++) if (real[i] === want) { const [x, y] = at(i); g.fillRect(x - r / 2, y - r / 2, r, r); }
      }
      return o;
    };
    function build() {
      const c = sides[0].dots; W = c.clientWidth; H = c.clientHeight; if (!W) return;
      dpr = Math.min(2, devicePixelRatio || 1); sx = W / COLS; sy = H / ROWS; dd = Math.max(.9, Math.min(sx, sy) * .52);
      for (const s of sides) { s.dots.width = W * dpr; s.dots.height = H * dpr; s.cpu.width = s.cpu.clientWidth * dpr; s.cpu.height = s.cpu.clientHeight * dpr; }
      L = { base: layer(.13, .5), lit: layer(.85, 1), probes: layer(.13, 0), reals: layer(0, .62) };
    }
    const fmt = n => Math.round(n).toLocaleString('en-US');
    /* CPU, sampled on a fixed grid so the trace scrolls instead of shimmering */
    const cpuB = i => { const ph = (i / RATE) % 1; return ph < .85 ? 16.6 + 5 * h(i) : 4 + 2 * h(i); };
    const bump = new Float32Array(600 * RATE + 16); for (const p of pings) { const i = Math.round(p.t * RATE); for (let k = 0; k < 9; k++) bump[i + k] += 3.2 * (1 - k / 9); }
    const cpuA = i => 1.05 + .5 * h(i) + (bump[i] || 0);
    function trace(cv, f, t) {
      const g = cv.getContext('2d'), w = cv.width / dpr, ht = cv.height / dpr; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, ht);
      const i1 = Math.floor(t * RATE), i0 = Math.floor((t - SPAN) * RATE) - 1, X = i => w - (t - i / RATE) / SPAN * w, Y = v => ht - 1.5 - v / 24 * (ht - 4);
      g.beginPath(); for (let i = i0; i <= i1; i++) { const x = X(i), y = Y(f(i)); i === i0 ? g.moveTo(x, y) : g.lineTo(x, y); }
      g.strokeStyle = 'rgba(255,255,255,.85)'; g.lineWidth = 1.2; g.lineJoin = 'round'; g.stroke();
      g.lineTo(X(i1), ht); g.lineTo(X(i0), ht); g.closePath();
      const gr = g.createLinearGradient(0, 0, 0, ht); gr.addColorStop(0, 'rgba(255,255,255,.16)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fill();
      g.fillStyle = 'rgba(255,255,255,.08)'; g.fillRect(0, ht - .5, w, .5);
    }
    function before(s, t) {
      const g = s.dots.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H); g.drawImage(L.base, 0, 0, W, H);
      const ph = t % 1, SW = .85, p = Math.min(1, ph / SW), xs = p * W, n = 18, tw = W * .34, fade = ph < SW ? 1 : Math.max(0, 1 - (ph - SW) / .15);
      for (let k = 0; k < n; k++) {
        const x1 = xs - k * tw / n, x0 = Math.max(0, x1 - tw / n); if (x1 <= 0) break;
        g.globalAlpha = Math.pow(1 - k / n, 2.2) * fade; g.drawImage(L.lit, x0 * dpr, 0, (x1 - x0) * dpr, H * dpr, x0, 0, x1 - x0, H);
      }
      g.globalAlpha = 1;
      if (ph < SW) { const gr = g.createLinearGradient(xs - 30, 0, xs, 0); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(1, 'rgba(255,255,255,.1)'); g.fillStyle = gr; g.fillRect(xs - 30, 0, 30, H); g.fillStyle = 'rgba(255,255,255,.75)'; g.fillRect(xs - .5, 0, 1, H); }
      setText(s.n, fmt(N * p));
    }
    function after(s, t, life) {
      const g = s.dots.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      const d = clamp((life - .5) / 1.9);
      if (d <= 0) g.drawImage(L.probes, 0, 0, W, H);
      else if (d < 1) {           /* the probes let go, a wave from the left */
        g.fillStyle = '#fff';
        for (let i = 0; i < N; i++) { if (real[i]) continue; const a = .13 * (1 - clamp((d * 1.4 - wave[i]) / .4)); if (a < .004) continue; g.globalAlpha = a; const [x, y] = at(i); g.fillRect(x - dd / 2, y - dd / 2, dd, dd); }
        g.globalAlpha = 1;
      }
      g.drawImage(L.reals, 0, 0, W, H);
      let read = 0;
      if (d >= 1) for (const p of pings) {
        const a = t - p.t; if (a < 0) break; if (a < 1) read++; if (a > 1.1) continue;
        const [x, y] = at(p.i), k = 1 - a / 1.1, r = 2 + 13 * eo(a, .9);
        g.globalAlpha = .7 * k; g.strokeStyle = '#fff'; g.lineWidth = 1; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.stroke();
        g.globalAlpha = k; g.fillStyle = '#fff'; g.shadowColor = 'rgba(255,255,255,.9)'; g.shadowBlur = 8; g.fillRect(x - dd * 1.3, y - dd * 1.3, dd * 2.6, dd * 2.6); g.shadowBlur = 0;
      }
      g.globalAlpha = 1;
      setText(s.n, d < 1 ? fmt(N * (1 - d)) : fmt(read));
    }
    let t0 = null, last = -9;
    const draw = (t, life) => { if (!W) build(); if (!W) return; for (const s of sides) { s.after ? after(s, t, life) : before(s, t); trace(s.cpu, s.after ? cpuA : cpuB, t); } };
    new ResizeObserver(() => { build(); if (REDUCE) draw(3.62, 9); }).observe(fig);
    TW.ticker(fig, P => {
      if (REDUCE) { draw(3.62, 9); return false; }
      if (P - last > 1.5) t0 = P;          /* back on screen: the probes let go again */
      last = P; const life = P - t0; draw(life < 3 ? life : 3 + (life - 3) % 590, life);
      return true;
    });
  }
}
/* the numbers: ratios count up, meters settle from 3.1 to 4.0, the small figures count down */
{
  const easeOut = p => 1 - Math.pow(1 - p, 4);
  const run = (ms, fn) => { const t0 = performance.now(); const step = t => { const p = Math.min(1, (t - t0) / ms); fn(easeOut(p)); if (p < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); };
  const dec = v => (String(v).split('.')[1] || '').length;
  const put = (fmt, v, d) => fmt.replace('{}', v.toFixed(d));
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return; io.unobserve(e.target); const c = e.target;
    $$('.cu', c).forEach(u => {
      const raw = u.dataset.v, n = parseFloat(raw), d = dec(raw);
      if (REDUCE || !n) return; u.style.minWidth = u.getBoundingClientRect().width + 'px';
      run(1300, k => setText(u, (n * k).toFixed(d)));
    });
    $$('.shr', c).forEach(m => {
      const a = +m.dataset.from, b = +m.dataset.to, f = b / a, d = Math.max(dec(m.dataset.from), dec(m.dataset.to)), v = $('.v', m);
      if (REDUCE) return;
      setTimeout(() => run(1800, k => { m.style.setProperty('--f', (1 + (f - 1) * k).toFixed(4)); setText(v, put(m.dataset.fmt, a + (b - a) * k, d)); }), 250);
    });
    $$('.cd', c).forEach(b => {
      if (REDUCE) return;
      if (b.hasAttribute('data-swap')) { setTimeout(() => b.classList.add('go'), 700); return; }
      const a = +b.dataset.from, z = +b.dataset.to;
      run(1500, k => setText(b, put(b.dataset.fmt, Math.round(a + (z - a) * k), 0)));
    });
  }), { threshold: .55 });
  /* before they are seen, each figure stands where 3.1 left it */
  if (!REDUCE) {
    $$('.shr').forEach(m => { m.style.setProperty('--f', '1'); setText($('.v', m), put(m.dataset.fmt, +m.dataset.from, Math.max(dec(m.dataset.from), dec(m.dataset.to)))); });
    $$('.cd').forEach(b => { if (b.hasAttribute('data-swap')) b.classList.add('arm'); else setText(b, put(b.dataset.fmt, +b.dataset.from, 0)); });
  }
  $$('.gain, .met').forEach(c => io.observe(c));
}
/* the constellation pulses only while it is on screen */
{
  const o = $('.orbit');
  if (o) new IntersectionObserver(es => es.forEach(e => o.classList.toggle('run', e.isIntersecting && !REDUCE))).observe(o);
}

/* ── the rest: copy, your system, the nav ── */
$$('.cmd').forEach(c => { const b = $('.cp', c); if (!b) return; b.onclick = async () => {
  try { await navigator.clipboard.writeText(c.dataset.copy); } catch (e) { const r = document.createRange(); r.selectNodeContents($('code', c)); getSelection().removeAllRanges(); getSelection().addRange(r); }
  b.classList.add('done'); setText($('span', b), T('Copied')); clearTimeout(b._t); b._t = setTimeout(() => { b.classList.remove('done'); setText($('span', b), T('Copy')); }, 1600); }; });
{
  const oss = $('.oss');
  if (oss) {
    const lit = $('.lit', oss);
    const pick = (k, anim) => { $$('button', oss).forEach(b => { const on = b.dataset.os === k; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); if (on) { if (!anim) lit.style.transition = 'none'; lit.style.width = b.offsetWidth + 'px'; lit.style.transform = `translateX(${b.offsetLeft - 4}px)`; if (!anim) { void lit.offsetWidth; lit.style.transition = ''; } } }); $$('.inst-p').forEach(p => p.classList.toggle('on', p.dataset.p === k)); };
    $$('button', oss).forEach(b => b.onclick = () => pick(b.dataset.os, true));
    const ua = navigator.userAgent, guess = /Windows/.test(ua) ? 'win' : /Linux|X11/.test(ua) && !/Android/.test(ua) ? 'linux' : 'mac';
    requestAnimationFrame(() => pick(guess, false)); document.fonts?.ready.then(() => pick($('button.on', oss).dataset.os, false));
    addEventListener('resize', () => pick($('button.on', oss).dataset.os, false));
  }
}
$$('[data-mark-nav]').forEach(e => TW.radar(e, 'clear', { still: true }));
wake();
})();
