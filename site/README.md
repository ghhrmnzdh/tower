# Tower — the site

One self-contained landing page: `index.html`. All CSS and JS are inline, there
is no build step, and **no third-party origin is contacted** — the fonts are
served from this folder.

The radar and the four model marks are ported 1:1 from `src/Glyph.swift` /
`Tower Identity Study.html`, so the page animates the *real* identity rather than
a picture of it. Everything else on the page describes behavior that actually
ships — if the guard, the weather, usage, or the agent monitor change, the copy
here has to follow.

## What's in here

```
index.html            the page (English)
fa/index.html         the Persian edition (RTL)
og.html               source for og.png            ← not published
og-fa.html            source for og-fa.png         ← not published
icon.html             source for apple-touch-icon  ← not published
og.png                1200×630 social card
og-fa.png             1200×630 social card (Persian)
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
wordmark stays Latin.

## Design notes

- **Dark instrument, not dark SaaS.** One flat panel primitive (`.well`,
  `--panel #08080a`, hairline borders). Glass (`backdrop-filter`) is spent in
  exactly **three** places — the nav, the popover replica, the final CTA. Adding
  a fourth is how this page drifted into looking generic the first time.
- **No card grids, no hover-lifts.** Sections are flat rows with hairline
  dividers — the same layout law the real popover follows (`docs/DESIGN.md`:
  "flat rows + dividers, Wi-Fi-menu style, no card chrome"). Hover brightens a
  hairline; it never floats a card.
- **Mono is the structural voice.** Every label, readout and annotation is
  JetBrains Mono — the same face the app bundles for its model/effort chips. The
  section name sits *on* the rule between bands (`.brule`), so no section needs a
  repeated kicker/eyebrow of its own.
- **Color is status, never decoration.** Green/amber/red/purple appear only where
  they carry the meaning they carry in the app. The tier accents
  (gold/rosso/steel/crayon) appear only on the model *labels*, never on a mark.
- **One loudest thing.** An `IntersectionObserver` keeps alive only the
  instruments that are on screen; everything else freezes, and the rAF loop stops
  entirely when the tab is hidden or nothing visible is animating. Reduce Motion
  freezes every mark at a legible still frame.

## Preview

```bash
python3 -m http.server -d site 8080     # → http://localhost:8080
```

## Regenerating the assets

One-off asset steps, not a build step. Run from the repo root.

```bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# og.png / og-fa.png — 1200×630 social cards (English, Persian)
for L in "" "-fa"; do
  "$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --virtual-time-budget=3000 --window-size=1200,630 \
    --screenshot="$PWD/site/og$L.png" "file://$PWD/site/og$L.html"
done

# apple-touch-icon.png — 180×180
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
`icon.html`, adds `.nojekyll`, and force-pushes an orphan commit to the
**`gh-pages`** branch. GitHub Pages is set to *Deploy from a branch →
`gh-pages` / root* — **not** "GitHub Actions" as the source. It can also be run
by hand from the Actions tab.

Live at `https://ghhrmnzdh.github.io/tower/`.

After a deploy:

```bash
git fetch origin && git ls-tree origin/gh-pages --name-only   # no README/og.html/icon.html
curl -sI https://ghhrmnzdh.github.io/tower/sitemap.xml
```

Then run the live URL through the Rich Results Test (both `SoftwareApplication`
and `FAQPage` should parse) and an OG debugger.

**One caveat about `robots.txt`:** crawlers only read it at the *origin root*
(`ghhrmnzdh.github.io/robots.txt`), which this repo doesn't control — so the copy
here is inert until Tower has a custom domain. Sitemap discovery comes from
submitting it in **Google Search Console** instead (URL-prefix property, verified
with a `google-site-verification` meta tag in `index.html`'s head).

## The download button

Every "Download Tower.app" points at `releases/latest`, which redirects to the
releases page while no release exists. To make it a real download:

```bash
./build.sh
ditto -c -k --keepParent Tower.app Tower.app.zip
gh release create v0.1.0 Tower.app.zip -t "Tower 0.1.0" -n "First public build."
```

## Editing

- **Tokens** are the `:root` block at the top of `index.html`.
- **The marks** are `radarSVG` / `drawRadar` / `modelSVG` / `drawModel` in the
  inline `<script>` — keep them in sync with `src/Glyph.swift` if the identity
  changes.
- **The FAQ** is mirrored into a `FAQPage` JSON-LD block, and the schema text
  must stay **identical** to the visible answer — a mismatch is a spam signal.
  Edit both, or neither.
