"""PlexAmp status probing and the browser-OAuth claim/pin flow for the streamer UI."""

import os
import socket
import subprocess
import uuid
from importlib.metadata import version as _pkg_version
from typing import Literal, Optional

import httpx

import audera

_PLEX_CLIENT_ID = str(uuid.uuid4())
_PLEX_HEADERS = {
    'X-Plex-Product': audera.NAME,
    'X-Plex-Version': _pkg_version('audera'),
    'X-Plex-Client-Identifier': _PLEX_CLIENT_ID,
    'X-Plex-Platform': 'Linux',
    'Accept': 'application/json',
}


def _plexamp_state() -> Literal['inactive', 'unclaimed', 'claimed']:
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'plexamp'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip() != 'active':
            return 'inactive'
    except Exception:
        return 'inactive'
    try:
        with socket.create_connection(('127.0.0.1', audera.PLEXAMP_PORT), timeout=1):
            return 'claimed'
    except OSError:
        return 'unclaimed'


def _create_plex_pin() -> tuple[int, str]:
    resp = httpx.post(
        'https://plex.tv/api/v2/pins',
        params={'strong': 'true'},
        headers=_PLEX_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['id'], data['code']


def _poll_plex_pin(pin_id: int) -> Optional[str]:
    resp = httpx.get(
        f'https://plex.tv/api/v2/pins/{pin_id}',
        headers=_PLEX_HEADERS,
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json().get('authToken') or None


def _get_claim_token(auth_token: str) -> str:
    resp = httpx.get(
        'https://plex.tv/api/claim/token.json',
        headers={**_PLEX_HEADERS, 'X-Plex-Token': auth_token},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['token']


def _restart_plexamp_with_claim(claim_token: str) -> None:
    subprocess.run(['systemctl', 'stop', 'plexamp'], timeout=15, check=True)
    override_dir = '/etc/systemd/system/plexamp.service.d'
    os.makedirs(override_dir, exist_ok=True)
    with open(f'{override_dir}/claim.conf', 'w') as f:
        f.write(f'[Service]\nEnvironment=PLEXAMP_CLAIM_TOKEN={claim_token}\n')
    subprocess.run(['systemctl', 'daemon-reload'], timeout=10, check=True)
    subprocess.run(['systemctl', 'start', 'plexamp'], timeout=10, check=True)


def _remove_claim_override() -> None:
    override = '/etc/systemd/system/plexamp.service.d/claim.conf'
    if os.path.exists(override):
        os.remove(override)
    subprocess.run(['systemctl', 'daemon-reload'], timeout=10)
