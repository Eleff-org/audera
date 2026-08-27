#!/usr/bin/env python3
"""Verify the assembled site builds and serves.

- **Layer A — reference resolution.** Extract every local ref from each page
  (``_site/*.html`` — ``href``/``src``) and ``brand/tokens.css`` (``url()``) and
  assert each resolves under ``_site/``. A new ``<img>``/link/``@font-face`` the
  build forgets to copy fails here instead of shipping a broken link.
- **Layer B — serve smoke test.** Serve ``_site/`` over HTTP and fetch ``/``
  plus every ref from Layer A, asserting ``200`` — what GitHub Pages does.
"""

from __future__ import annotations

import re
import sys
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8123  # fixed high port; avoids clashing with anything else on the runner

# Build-generated files that aren't href/src refs Layer A discovers, but must serve.
EXTRA = ['/robots.txt', '/sitemap.xml', '/llms.txt']


def collect_refs(site: Path) -> list[str]:
    """Extract local references and assert each resolves under ``_site/``.

    Args:
        site: The assembled ``website/_site`` directory.

    Returns:
        The de-duplicated server-root-relative URL paths (e.g.
        ``/assets/players.png``), in first-seen order.

    Raises:
        SystemExit: If any reference does not resolve on disk.
    """
    errors: list[str] = []
    urls: list[str] = []

    def add(url_path: str, fs_path: Path) -> None:
        if not fs_path.is_file():
            errors.append(f'{url_path} -> missing {fs_path}')
        elif url_path not in urls:
            urls.append(url_path)

    # HTML: href/src on every page, relative to the site root (pages live at _site/).
    for page in sorted(site.glob('*.html')):
        html = page.read_text(encoding='utf-8')
        for ref in re.findall(r'(?:href|src)="([^"]+)"', html):
            if ref.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            add('/' + ref.lstrip('/'), site / ref.lstrip('/'))

    # CSS: url(), relative to _site/brand/ (where tokens.css lives).
    css = (site / 'brand' / 'tokens.css').read_text(encoding='utf-8')
    for ref in re.findall(r'url\(([^)]+)\)', css):
        ref = ref.strip().strip('\'"')
        if ref.startswith(('http:', 'https:', 'data:')):
            continue
        add('/brand/' + ref.lstrip('/'), (site / 'brand' / ref.lstrip('/')).resolve())

    if errors:
        print('Unresolved references:', file=sys.stderr)
        for error in errors:
            print(f'  {error}', file=sys.stderr)
        raise SystemExit(1)

    return urls


class _QuietHandler(SimpleHTTPRequestHandler):
    """A request handler that does not log every request to stderr."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, D102 - silence access log
        pass


def serve_and_fetch(site: Path, urls: list[str]) -> None:
    """Serve ``_site/`` and assert ``/``, each URL, and each ``EXTRA`` path ``200``.

    Args:
        site: The assembled ``website/_site`` directory to serve verbatim.
        urls: The server-root-relative URL paths from :func:`collect_refs`.
            The build-generated ``EXTRA`` paths (``robots.txt``, ``sitemap.xml``,
            ``llms.txt``) are also fetched — they aren't ``href``/``src`` refs.

    Raises:
        SystemExit: If any URL returns a non-``200`` status.
    """
    handler = partial(_QuietHandler, directory=str(site))
    server = ThreadingHTTPServer(('127.0.0.1', PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(f'Serving {site} on :{PORT} and fetching:')
        failed = False
        for path in ['/', *urls, *EXTRA]:
            code = _fetch_status(f'http://127.0.0.1:{PORT}{path}')
            if code == 200:
                print(f'  200 {path}')
            else:
                print(f'  {code} {path}  <-- expected 200', file=sys.stderr)
                failed = True
        if failed:
            print('Serve smoke test failed.', file=sys.stderr)
            raise SystemExit(1)
    finally:
        server.shutdown()


def _fetch_status(url: str) -> int:
    """Return the HTTP status for ``url`` (``0`` if the request could not run).

    The body is drained before the response closes so the server finishes
    sending the file rather than logging a ``BrokenPipeError`` when the client
    hangs up mid-transfer (visible on the larger assets — the image and fonts).
    """
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310 - fixed localhost URL
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return 0


def main() -> None:
    """Run reference resolution then the serve smoke test against ``_site/``."""
    site = Path(__file__).resolve().parent.parent / 'website' / '_site'
    if not site.is_dir():
        print(f'Missing {site} — run website/build.py first.', file=sys.stderr)
        raise SystemExit(1)

    urls = collect_refs(site)
    print('Verified references resolve:')
    for url in urls:
        print(f'  {url}')

    serve_and_fetch(site, urls)
    print('OK — site builds and serves.')


if __name__ == '__main__':
    main()
