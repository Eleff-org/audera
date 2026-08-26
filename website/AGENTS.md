# Website

The public site is a single hand-written static page — `website/index.html` — plus the
image it shows (`assets/players.png`) and the brand assets it consumes from `brand/` (see
`brand/AGENTS.md`). No framework, no build step beyond copying files, no server. The page
links out to the developer docs on `main` in GitHub rather than republishing them, so there
are no doc copies to keep in sync.

## Links out to GitHub

The nav and CTA point at Markdown on `main`, which GitHub renders:

- **Docs** → `docs/README.md` (the docs landing hub).
- **Get started** → `docs/getting-started.md` (the end-user guide).
- **GitHub ↗** → the repository root.

Because these resolve against `main`, they only work once the branch is merged. Edit the
docs under `docs/`, not here.

## Brand assets

`index.html` links `brand/tokens.css` relative to itself, and `tokens.css` references its
fonts as `fonts/<file>` relative to itself. The image radius uses `--radius-media` (the
one rounded shape in an otherwise-square system). Nothing is hard-coded — all palette,
type, and shape come from `brand/tokens.css`.

## Build

`website/build.py` assembles `website/_site/` (the Pages upload root): it copies
`index.html` and `assets/` in, copies `brand/tokens.css` → `_site/brand/tokens.css` and
`brand/fonts/*.woff2` → `_site/brand/fonts/`, and drops a `.nojekyll` marker so Pages
serves the tree verbatim. Both workflows call this one script — there is no duplicated copy
logic. Stdlib only, run via `uv run --no-project python website/build.py`. `_site/` and any
local `brand/` copy are gitignored.

`website/verify.py` runs **after** `build.py` in both workflows (single source of truth for
the check) and asserts the site actually works, not just that files exist. Layer A extracts
every local ref from `_site/index.html` (`href`/`src`) and `_site/brand/tokens.css`
(`url()`) and fails if any doesn't resolve under `_site/` — so a new `<img>`, link, or
`@font-face` the build forgets to copy is caught instead of shipping broken. Layer B serves
`_site/` over HTTP and fetches `/` plus every ref from Layer A, asserting `200`, mirroring
Pages. It requires `build.py` to have run first and errors clearly if `_site/` is absent.
Stdlib only — run it with `uv run --no-project python website/verify.py`. Both scripts are
stdlib-only, so the workflows install uv but skip `uv sync`.

## Local preview

```bash
uv run --no-project python website/build.py   # assembles website/_site/
# open website/_site/index.html in a browser, or serve it:
python -m http.server -d website/_site 8000    # then http://127.0.0.1:8000
```

Fonts and tokens resolve because `_site/brand/` sits beside `index.html`. Screenshot with
the headless-Chrome recipe in `audera/ui/AGENTS.md`, pointed at the served port. The mobile
crop/fade is hard to verify headless — check it in a device emulator.

## CI/CD

- **Build check** (`website-build.yml`): push to `main` and PRs touching `brand/**` or
  `website/**`; runs `website/build.py` then `website/verify.py` (reference resolution +
  serve smoke test) and fails if the site doesn't build or serve. No deploy.
- **Release deploy** (`website-publish.yml`): `v*` tag or `workflow_dispatch`; runs the same
  build + verify, then deploys `website/_site` to GitHub Pages — so a broken site fails
  before it reaches Pages. Concurrency group `pages-deploy` serializes deploys.
- The `github-pages` environment has a required reviewer (configured in GitHub settings),
  so a tag-triggered deploy pauses for approval. Pages source is GitHub Actions, with no
  `gh-pages` branch.

## Domain

`audera-audio.com` via Cloudflare DNS to GitHub Pages (A records to `185.199.108-111.153`,
or CNAME to `eleff-org.github.io`). SSL/TLS Full, HTTPS enforced.
