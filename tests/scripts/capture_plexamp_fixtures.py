"""
Captures real PlexAmp headless HTTP responses and writes them as fixture files.

Usage:
    uv run python tests/scripts/capture_plexamp_fixtures.py [host] [port]

Defaults to the AUDERA_PLEXAMP_HOST env var (or 192.168.1.35) at port 32500.
Requires PlexAmp headless to be running and reachable. Run while a track is
actively playing to capture a non-empty timeline response.

Fixtures are written to tests/fixtures/plexamp/.
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

HOST = sys.argv[1] if len(sys.argv) > 1 else os.getenv('AUDERA_PLEXAMP_HOST', '192.168.1.35')
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 32500
BASE = f'http://{HOST}:{PORT}'

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'plexamp'
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def _get(path: str, params: dict | None = None) -> tuple[int, str]:
    url = f'{BASE}{path}'
    print(f'GET {url}  params={params}')
    response = httpx.get(url, params=params, timeout=10)
    print(f'  -> {response.status_code}  body: {response.text[:200]}')
    return response.status_code, response.text


def _save_xml(name: str, text: str) -> None:
    dest = FIXTURES_DIR / f'{name}.xml'
    dest.write_text(text)
    print(f'  saved -> {dest}')


def _save_json(name: str, data: dict) -> None:
    dest = FIXTURES_DIR / f'{name}.json'
    dest.write_text(json.dumps(data, indent=2))
    print(f'  saved -> {dest}')


def main():
    print(f'\nCapturing PlexAmp fixtures from {BASE}\n')

    # Timeline poll — the primary now-playing endpoint
    status, body = _get(
        '/player/timeline/poll',
        params={'wait': '0', 'commandID': '1', 'includeMetadata': '1'},
    )

    if status == 200:
        # Heuristic: if any Timeline has state="playing" it's active
        if 'state="playing"' in body:
            _save_xml('timeline_active', body)
            print('  (active timeline captured — track is playing)')
        else:
            _save_xml('timeline_idle', body)
            print('  WARNING: no active playback found; saved as timeline_idle.xml')
            print('  Play a track then re-run to capture timeline_active.xml')
    else:
        print(f'  ERROR: timeline/poll returned {status}')

    # Capture playback command endpoint shapes
    for endpoint, name in [
        ('/player/playback/play', 'play'),
        ('/player/playback/pause', 'pause'),
        ('/player/playback/skipNext', 'skip'),
    ]:
        try:
            _, resp_body = _get(endpoint, params={'commandID': '1', 'machineIdentifier': 'audera-capture'})
            _save_json(name, {'_raw': resp_body})
        except Exception as exc:
            print(f'  WARNING: {endpoint} failed: {exc}')

    print('\nDone. Commit tests/fixtures/plexamp/ alongside test_plexamp.py.')


if __name__ == '__main__':
    main()
