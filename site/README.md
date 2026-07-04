# Tower — showcase site

A single, self-contained landing page for Tower: what the problem is, how Tower
helps, the Mac app and the terminal dashboard, the model marks, and a roadmap.

Everything is in **`index.html`** — one file. The radar and the four model marks
are ported 1:1 from `src/Glyph.swift` / `Tower Identity Study.html`, so the page
animates the *real* identity, not a mockup of it. The only external request is a
Google Fonts stylesheet (Newsreader + JetBrains Mono); it degrades to system
serif/mono if that ever fails to load.

## Preview locally

```bash
open site/index.html          # or: python3 -m http.server -d site 8080
```

## Deploy to GitHub Pages

**Option A — the workflow (recommended, keeps the site in `site/`).**
A ready workflow lives at `.github/workflows/deploy-site.yml`. Once:

1. Push to `main`.
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.

Every push that touches `site/` republishes. Your page:
`https://ghhrmnzdh.github.io/tower/`.

**Option B — no workflow, serve from the repo root.**
GitHub's "Deploy from a branch" only serves the root or `/docs`, so copy the
file up and point Pages at the root:

```bash
cp site/index.html index.html
git add index.html && git commit -m "Publish site" && git push
```

Then **Settings → Pages → Deploy from a branch → `main` / `root`**.

**Option C — a `gh-pages` branch.**

```bash
git subtree push --prefix site origin gh-pages
```

Then **Settings → Pages → Deploy from a branch → `gh-pages` / `root`**.

## The download button

Both "Download Tower.app" buttons point at
`https://github.com/ghhrmnzdh/tower/releases/latest`. With no releases yet that
redirects to the releases page. To make it a real download, cut a release and
attach the app:

```bash
./build.sh
ditto -c -k --keepParent Tower.app Tower.app.zip
gh release create v0.1.0 Tower.app.zip -t "Tower 0.1.0" -n "First public build."
```

"Build from source" and "View source" already resolve — they point at the repo
and the `git clone … && ./build.sh` one-liner.

## Editing

- **Colors / type** are CSS variables at the top of `index.html` (`:root`) — all
  brand-derived (ink, amber, red, the four model accents).
- **The marks** are the `buildRadar` / `buildModel` functions in the inline
  `<script>`; keep them in sync with `Glyph.swift` if the identity changes.
- **Copy** lives inline in the HTML sections; the roadmap cards are the
  `.road` grid.
