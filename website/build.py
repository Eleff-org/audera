#!/usr/bin/env python3
"""Build the static site for GitHub Pages."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

SITE_URL = 'https://audera-audio.com'


def main() -> None:
    """Copy the page and brand assets into a fresh ``website/_site/``."""
    # Resolve paths relative to the repo root (this script lives in website/).
    root = Path(__file__).resolve().parent.parent
    website = root / 'website'
    site = website / '_site'

    # Fresh build directory every run.
    shutil.rmtree(site, ignore_errors=True)
    (site / 'assets').mkdir(parents=True)
    (site / 'brand' / 'fonts').mkdir(parents=True)

    # Every top-level page (index.html plus the features-*.html mockups) and images.
    for page in sorted(website.glob('*.html')):
        shutil.copy(page, site / page.name)
    for asset in (website / 'assets').iterdir():
        shutil.copy(asset, site / 'assets' / asset.name)

    # Brand tokens + self-hosted fonts, keeping tokens.css beside fonts/.
    shutil.copy(root / 'brand' / 'tokens.css', site / 'brand' / 'tokens.css')
    for font in (root / 'brand' / 'fonts').glob('*.woff2'):
        shutil.copy(font, site / 'brand' / 'fonts' / font.name)

    # SEO + agentic-discoverability files (skip silently if a source is absent).
    for name in ('robots.txt', 'llms.txt'):
        if (website / name).exists():
            shutil.copy(website / name, site / name)

    # Generate sitemap.xml from the same page glob (one source of truth, can't drift).
    urls: list[str] = []
    for page in sorted(website.glob('*.html')):
        loc = SITE_URL + '/' if page.name == 'index.html' else f'{SITE_URL}/{page.name}'
        lastmod = datetime.fromtimestamp(page.stat().st_mtime, tz=timezone.utc).date().isoformat()
        urls.append(f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>')
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(urls) + '\n</urlset>\n'
    )
    (site / 'sitemap.xml').write_text(sitemap, encoding='utf-8')

    # Serve the directory verbatim (no Jekyll processing on Pages).
    (site / '.nojekyll').touch()

    print(f'Built {site}')


if __name__ == '__main__':
    main()
