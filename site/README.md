# Tower — the site

Two pages, `index.html` and `fa/index.html`, sharing one stylesheet and two
scripts (`app.css`, `app.js`, `anatomy.js`). There is no build step, and **no
third-party origin is contacted**: the fonts are served from this folder.

The page is a **showcase of the real app, running**. Every window on it is a
replica of an actual Tower surface, built from the same panel vocabulary as
`src/Dashboard.swift` / `src/Popover.swift` and fed by one fictional working day
(a product team's repos, never the maintainer's own, in a made-up Toronto
session), so the numbers agree on every surface. Nothing on
the page comes from a real machine: screenshots of the app were used only to
match its layout. The radar and the four model marks are ported 1:1 from
`src/Glyph.swift`. The terminal frames are not drawn by hand at all: they are
composed by the real `src/tower-tui.py` (see *The terminal frames* below).
Everything on the page describes behavior that actually ships. If the guard,
the weather, usage, or the agent monitor change, the copy here has to follow.

## What's in here

```
index.html            the page (English)
fa/index.html         the Persian edition (RTL)
app.css               every style, both pages (tokens at the top)
app.js                marks, the working day, the popover/menu-bar/dashboard
                      replicas, the director (hero + OG), page wiring
anatomy.js            the "How it works" figure
tools/tui-frames.py   re-renders the terminal frames from src/tower-tui.py  ← not published
tools/fixture.py      the fictional working day those frames show           ← not published
tools/shot.mjs        headless screenshots + console errors, for looking    ← not published
tools/og.mjs          renders the social cards and videos from og.html      ← not published
og.html               source for og(-fa).png and og(-fa).mp4 (?lang=fa)  ← not published
icon.html             source for apple-touch-icon  ← not published
og.png                1200×630 social card
og-fa.png             1200×630 social card (Persian)
og.mp4                1200×630 social video, 12 s loop, 60 fps, H.264
og-fa.mp4             1200×630 social video (Persian)
favicon.svg           the radar mark (theme-aware)
apple-touch-icon.png  180×180, on ink
robots.txt sitemap.xml
fonts/                self-hosted woff2 + licenses
README.md             this file                    ← not published
```

The **Persian edition** (`fa/`) is its own edition, not a translation laid over
Latin metrics: body text is set in **Vazirmatn** and display headings in
**Estedad** (both self-hosted, OFL), and headings run at normal tracking —
Latin's negative letter-spacing would pinch the cursive joins. Both faces are
scoped to the Arabic Unicode block, so Latin product terms (Agent, Claude,
macOS) inside the RTL flow fall through to SF Pro / Inter, and the "Tower"
wordmark stays Latin. The app replicas stay English and `dir="ltr"`, as the app
itself is.

## Design notes

- **The popover is the heart.** The hero is the menu bar with Tower's item and
  its popover dropping open over a desk, with the real terminal dashboard
  frosted behind it. Callouts on either side name what each part says. The same
  glass, radius and hairlines carry through every card on the page.
- **One director, a function of time.** The hero and the social video are
  driven by `heroScript(t)` / `ogScript(t)` in `app.js`: springs and windows,
  no timers, so any instant can be drawn exactly. The hero loops a needs-you,
  an off-country hold and a no-path hold; the radar, the header, the network
  row, the location row, the plan and the callouts all crossfade between the
  same weights (`stackTo`).
- **How it works is a machine, not a film.** `anatomy.js` draws Tower as a
  solid isometric figure in the manner of the Anatomy skill
  (github.com/wheresryan22/anatomy, MIT): Claude Code, Desktop and the web feed
  one track; the gate lifts only while the radar has the country confirmed and
  the probe has a path; held requests wait in the bay and go on by themselves;
  hooks light the agent board; `/usage` moves the gauge only while the gate is
  green. It tours pass → off-country → pass → no path on its own, and clicking
  the radar or the probe (or `G` / `N`) takes over for ten seconds. The geometry
  and the little engine are this page's own.
- **Faster is shown, not just stated.** The Faster section draws the same
  16,036 transcripts twice (`#scan` in `app.js`): 3.1 sweeps every one each
  second while its CPU trace sits near 17%; in 4.0 Tower's own 15,751 probes
  let go, and only a file that grew lights up, at about 1.5%. The meters start
  at the 3.1 value and settle on the 4.0 one. The numbers are the measured ones
  in the copy; keep the figure and the copy in step.
- **The platforms are logos.** macOS, Linux and Windows marks (`macos`, `tux`,
  `windows` in the symbol set) sit on the install tabs, the hero, the platform
  cards and a small constellation wired to the one daemon.
- **The app's own rules hold on the page.** The mark is the state; motion is a
  state change; failure never bounces; one loudest thing at a time. Amber is a
  hold, red is danger, green is only a switch that is on or a healthy link.
  Model marks are monochrome; tier colours appear only in the TUI.
- **A stable floor.** Working agents sit in the order they started, exactly as
  the app orders them. Only a needs-you event moves a row, and only upward.
- **Only what is seen runs.** Marks and tickers register with an
  `IntersectionObserver`; one rAF loop draws only visible, animating ones and
  stops when nothing on screen has anything to say or the tab is hidden.
  Reduced Motion (or `?motion=calm`) shows a still page, figure included.
- **Copy:** no em dashes, no exclamation marks. The app replicas keep the app's
  own strings (which do use "—"), stay English and stay `dir="ltr"` on the
  Persian page, as the app itself is.
- **Platforms, honestly.** The Mac app is Tower's own. Linux and Windows are
  **community editions** (Persian: کامیونیتی), and Windows is a preview that has
  never run on a real Windows PC. The page says so wherever they appear; never
  present them as equal to the Mac app.

## Preview

```bash
python3 -m http.server -d site 8080     # → http://localhost:8080  (/fa/ for Persian)
```

## The terminal frames

The Terminal scene, its hold step and the Windows card replay frames composed
by the real dashboard: `tools/tui-frames.py` imports `src/tower-tui.py` (never
runs it), calls `compose()` against `tools/fixture.py` at five sizes plus a held
screen, and splices the frames into each page's `tuiData` JSON block. HOME
points at an empty temp dir for the run, so nothing of yours is read, and the
clock is pinned to one instant (the network sparklines bin by wall time), so a
re-run is byte-identical and `--check` only fails on a real change.

```bash
python3 site/tools/tui-frames.py           # after any change to the TUI's layout
python3 site/tools/tui-frames.py --check   # exit 1 if a page's frames are stale
```

To look at the page headless (any size; prints page errors):

```bash
node site/tools/shot.mjs http://localhost:8080/ /tmp/shots "top|agents|terminal" 1440x900 black
```

## Regenerating the assets

One-off asset steps, not a build step. Run from the repo root.

### The social card and video

`og.html` is one 1200×630 scene built from the hero's own parts (`app.css`,
`app.js` with `window.TW_OG`): the headline, three live chips (the radar's
state, Internet, API) and the platforms on one side; the menu bar and the
popover, cropped at the card's edge, on the other. `ogScript(t)` plays a
12-second loop: the popover drops open, an approval rises with the badge in the
menu bar, the guard holds off-country and clears, then holds for no path and
clears, and the popover closes. Every motion is a pure function of time, so the
video has no seam and any instant can be drawn exactly. Open it in a browser to
watch it live; `?lang=fa` is the Persian edition (mirrored), `?t=4.3&cap=0` a
still (the card is that instant: someone is waiting on you).

```bash
node site/tools/og.mjs        # og.png, og-fa.png, og.mp4, og-fa.mp4 (needs ffmpeg)
node site/tools/og.mjs png    # the cards only
```

The video is rendered frame by frame at 2×, not screen-recorded, then
downsampled with Lanczos and encoded as H.264 (yuv420p, faststart) so every
player and link preview can show it. Both pages carry `og:video` tags next to
`og:image`; the card stays the image everywhere a video isn't played.

```bash
# apple-touch-icon.png — 180×180
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --virtual-time-budget=2000 --window-size=180,180 \
  --screenshot="$PWD/site/apple-touch-icon.png" "file://$PWD/site/icon.html"
```

### The fonts

**Sans** is the system stack first (`-apple-system` → SF Pro), because that is
what the app itself renders in; **Inter** is self-hosted and only fetched where
SF Pro doesn't exist. **Mono** is JetBrains Mono, subset from the very TTFs the
app bundles. **Persian** (`fa/`) leads with **Vazirmatn** — a variable OFL face,
Arabic subset only (`fonts/vazirmatn-arabic.woff2`, ~46 KB, weights 100–900) —
so the Persian edition has one consistent, premium face on every platform and in
the OG render, not whatever Arabic fallback the OS happens to ship.

```bash
# Vazirmatn — Arabic-subset variable woff2 (SIL OFL). Ships in @fontsource-variable.
curl -o site/fonts/vazirmatn-arabic.woff2 \
  "https://cdn.jsdelivr.net/npm/@fontsource-variable/vazirmatn/files/vazirmatn-arabic-wght-normal.woff2"
```

```bash
# Estedad — the Persian display face (SIL OFL), subset to the Arabic block
curl -sL -o /tmp/estedad.zip \
  "https://github.com/aminabedi68/Estedad/releases/download/8.5/Estedad-v8.5.zip"
unzip -o /tmp/estedad.zip -d /tmp/estedad-x
python3 -m fontTools.subset "/tmp/estedad-x/Estedad-v8.5/Estedad[wght].woff2" \
  --unicodes="U+0600-06FF,U+0750-077F,U+08A0-08FF,U+200C-200E,U+FB50-FDFF,U+FE70-FEFF" \
  --layout-features='*' --flavor=woff2 \
  --output-file=site/fonts/estedad-arabic.woff2
```

```bash
# Inter — Google's own latin-subset variable woff2, saved locally
curl -o site/fonts/inter-latin.woff2 \
  "https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7W0Q5nw.woff2"

# JetBrains Mono — subset from src/Fonts/*.ttf (needs `pip install fonttools brotli`)
UNI='U+0020-007E,U+00A0,U+00B7,U+00D7,U+2013,U+2014,U+2018,U+2019,U+201C,U+201D,U+2022,U+2026,U+2190-2193,U+2500-257F,U+2580-259F,U+25A0-25FF,U+2713,U+2717,U+26A0,U+26D4,U+00B0,U+25CF,U+25CB,U+21BB'
for W in Medium:500 Bold:700; do
  python3 -m fontTools.subset "src/Fonts/JetBrainsMono-${W%%:*}.ttf" \
    --unicodes="$UNI" --layout-features='kern,liga,calt' --flavor=woff2 \
    --output-file="site/fonts/jetbrainsmono-${W##*:}.woff2" --desubroutinize --no-hinting
done
```

The block glyphs (`█ ░ ▂▃▅▆`) are load-bearing — they draw the TUI replica's
usage bars and sparkline. Keep them in the subset range.

## Deploy

`.github/workflows/deploy-site.yml` fires on any push to `main` that touches
`site/**`. It copies `site/` to a temp dir, strips `README.md` / `og.html` /
`icon.html` / `tools/`, adds `.nojekyll`, and force-pushes an orphan commit to the
**`gh-pages`** branch. GitHub Pages is set to *Deploy from a branch →
`gh-pages` / root* — **not** "GitHub Actions" as the source. It can also be run
by hand from the Actions tab.

Live at `https://ghhrmnzdh.github.io/tower/`.

After a deploy:

```bash
git fetch origin && git ls-tree origin/gh-pages --name-only   # no README/og*.html/icon.html/tools
curl -sI https://ghhrmnzdh.github.io/tower/sitemap.xml
```

Then run the live URL through the Rich Results Test (both `SoftwareApplication`
and `FAQPage` should parse) and an OG debugger.

**One caveat about `robots.txt`:** crawlers only read it at the *origin root*
(`ghhrmnzdh.github.io/robots.txt`), which this repo doesn't control — so the copy
here is inert until Tower has a custom domain. Sitemap discovery comes from
submitting it in **Google Search Console** instead (URL-prefix property, verified
with a `google-site-verification` meta tag in `index.html`'s head).

## Release links

The page installs with one line per system. macOS runs `install.sh` (served
from this folder). Linux fetches `releases/latest/download/tower_all.deb`,
which exists only once a release made by `release.sh` has attached the `.deb`,
so cut a release before pointing people at the Linux tab. Windows clones the
repository and runs the TUI.

## Editing

- **Tokens** are the `:root` block at the top of `app.css`; the Persian faces
  and RTL rules sit under `html[lang=fa]`.
- **The working day** (agents, subagents, plan) is `TW.day` / `TW.agents` in
  `app.js`; keep it consistent with `tools/fixture.py`, which feeds the terminal.
- **The marks** are `drawRadar` / `drawModel` / `drawBeacon` in `app.js`; keep
  them in sync with `src/Glyph.swift` if the identity changes.
- **Strings a script writes** (Copy/Copied, the figure's readout) come from
  `window.TW_T` in each page, so the Persian page sets its own.
- **The FAQ** is mirrored into a `FAQPage` JSON-LD block, and the schema text
  must stay **identical** to the visible answer — a mismatch is a spam signal.
  Edit both, or neither.
