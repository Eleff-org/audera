# Website

The public site in `website/`, built with [Zensical](https://pypi.org/project/zensical/) (a Material for MkDocs distribution) and consuming brand tokens from `brand/` (see `brand/AGENTS.md`). It publishes the marketing pages plus the engineer docs: `website/docs/developer/*.md` are build-time copies of `docs/dev/*.md` (the source of truth), so edit the originals under `docs/dev/`. ADRs are not published.

Zensical is a **dev dependency only** (`zensical>=0.0.53` in `[dependency-groups] site`), installed with `uv sync --group site`; it is not a runtime dependency.

## Brand copy

`docs/stylesheets/brand.css` is a build-time **copy** of `brand/tokens.css` (symlinks are unreliable on Windows dev boxes), and `docs/stylesheets/fonts/` holds copied woff2 files; both are gitignored. `zensical.toml` and `extra.css` are self-documenting: `font = false` disables Material's font loader, and `extra.css` bridges brand tokens to Material's `--md-*` variables.

Likewise, `docs/developer/*.md` are build-time copies of the engineer docs under `docs/dev/` (also gitignored). The `nav` in `zensical.toml` references these copied paths, so copying them is a **prerequisite** for `zensical build` / `serve` to succeed. Edit the source files in `docs/dev/`, not the copies.

## Local dev

```bash
uv sync --group site
cp brand/tokens.css website/docs/stylesheets/brand.css
cp brand/fonts/*.woff2 website/docs/stylesheets/fonts/
mkdir -p website/docs/developer
cp docs/dev/DEVELOPMENT.md website/docs/developer/development.md
cp docs/dev/PROVISION.md website/docs/developer/provisioning.md
cp docs/dev/CLI.md website/docs/developer/cli.md
cd website && uv run zensical serve   # 127.0.0.1:8000; `zensical build` writes website/site/
```

Editing `website/docs/**` hot-reloads; editing `brand/tokens.css`, fonts, or the engineer docs under `docs/dev/` does **not**, because the served copies are stale, so re-run the `cp` commands after changing tokens, fonts, or developer docs. Screenshot with the headless-Chrome recipe in `audera/ui/AGENTS.md`, pointed at port 8000.

## CI/CD

- **Build check** (`website-build.yml`): push to `main` and PRs touching `brand/**`, `website/**`, or `docs/dev/**`; copies brand assets and the engineer docs, then runs `zensical build`. No deploy.
- **Release deploy** (`website-publish.yml`): `v*` tag or `workflow_dispatch`; builds and deploys to GitHub Pages. Concurrency group `pages-deploy` serializes deploys.
- The `github-pages` environment has a required reviewer (configured in GitHub settings), so a tag-triggered deploy pauses for approval. Pages source is GitHub Actions, with no `gh-pages` branch.

## Domain

`audera-audio.com` via Cloudflare DNS to GitHub Pages (A records to `185.199.108-111.153`, or CNAME to `eleff-org.github.io`). SSL/TLS Full, HTTPS enforced.
