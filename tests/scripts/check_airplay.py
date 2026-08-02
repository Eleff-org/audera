"""
Confirms the AirPlay source is advertising as AirPlay 2 and that Snapserver has registered it.

Usage:
    uv run --with pyatv python tests/scripts/check_airplay.py [--host <ip>]

`pyatv` is an AirPlay discovery client and not an Audera dependency, so it is supplied with
`--with`. Nothing here imports it at module scope, so `--help` works without it.

Defaults to the AUDERA_SNAPSERVER_HOST env var. With a `--host`, discovery is a unicast probe of
that address, which makes the script usable from a machine whose firewall drops inbound mDNS
(Windows, most VPNs). Pass `--scan` to sweep with multicast instead.

The device name and stream id are read from `audera.domains.sources.CATALOG`, the same URI the
device provisions shairport-sync with.

This script does not play audio. shairport-sync 4.3.7 in AirPlay 2 mode requires the transient
HAP pair-verify a real sender performs, and `pyatv`'s implementation of it is rejected with
`HTTP 400` on `/pair-pin-start`. Sending a tone needs an iPhone, iPad, or Mac. The checks here
cover everything up to the first byte of audio.

Exit status is 0 only when the receiver advertised AirPlay 2 and Snapserver knows the stream. A
receiver that advertises while Snapserver has no such stream is a `snapserver.conf` fault rather
than a shairport-sync fault.
"""

import argparse
import asyncio
import os
import sys
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

import audera
from audera.clients import SnapserverClient
from audera.domains.sources import CATALOG

load_dotenv()

_SOURCE_ID = 'AirPlay'

# The port the AirPlay entry's URI pins. shairport-sync on 5000 is AirPlay 1, which still plays
# from Apple hardware but with none of the AirPlay 2 behaviour.
_AIRPLAY_2_PORT = 7000


def _airplay_receiver_name() -> str:
    """Returns the name shairport-sync advertises, read from the catalog's AirPlay URI.

    `devicename` is shairport-sync's `--name` and is what iOS, and therefore `pyatv`, sees.
    `name` is the Snapcast stream id.
    """
    source = next(source for source in CATALOG if source.id == _SOURCE_ID)
    query = parse_qs(urlparse(source.uri).query)
    return query['devicename'][0]


async def _find_receiver(host: Optional[str], name: str, timeout: float):
    """Returns the `pyatv` config for the AirPlay receiver, or `None`.

    Scans for every protocol rather than filtering to RAOP, since whether an `_airplay._tcp`
    service is advertised is one half of the AirPlay 2 check.

    Parameters
    ----------
    host: `str | None`
        The address to probe directly, or `None` to sweep the network with multicast.
    name: `str`
        The advertised receiver name to match.
    timeout: `float`
        How long to wait for responses.
    """
    # `pyatv` is supplied with `--with` rather than pinned as a dependency, so the type checker
    # cannot resolve the import.
    import pyatv  # ty: ignore[unresolved-import]

    loop = asyncio.get_running_loop()
    found = await pyatv.scan(loop, timeout=timeout, hosts=[host] if host else None)

    if not found:
        return None
    # Match by name, then fall back to the sole result of a unicast probe, which can only have
    # found the probed address. A name mismatch is reported rather than treated as no receiver.
    for config in found:
        if config.name == name:
            return config
    if host and len(found) == 1:
        print(f'    note: receiver advertises {found[0].name!r}, expected {name!r}')
        return found[0]
    print(f'    found {[config.name for config in found]}, none named {name!r}')
    return None


def _check_advertisement(config) -> bool:
    """Reports whether the receiver advertises AirPlay 2, printing what it found either way.

    Parameters
    ----------
    config: `pyatv.interface.BaseConfig`
        The discovered receiver.
    """
    from pyatv.const import Protocol  # ty: ignore[unresolved-import]

    ok = True
    for protocol in (Protocol.RAOP, Protocol.AirPlay):
        service = config.get_service(protocol)
        if service is None:
            # `_airplay._tcp` absent with `_raop._tcp` present is the AirPlay 1 downgrade:
            # shairport-sync built without `--with-airplay-2`, reporting the same version string.
            print(f'[ FAIL ] No {protocol.name} service advertised')
            ok = False
        elif service.port != _AIRPLAY_2_PORT:
            print(f'[ FAIL ] {protocol.name} is on port {service.port}, expected {_AIRPLAY_2_PORT}')
            ok = False
        else:
            print(f'[  OK  ] {protocol.name} on port {service.port}')
    return ok


async def _check_stream(host: str) -> bool:
    """Reports whether Snapserver has registered the AirPlay stream, printing what it found.

    Parameters
    ----------
    host: `str`
        The Snapserver host.
    """
    client = SnapserverClient(host=host, port=audera.SNAPSERVER_PORT)
    try:
        status = await asyncio.to_thread(client.get_stream_status)
    except Exception as exc:
        print(f'[ FAIL ] Snapserver unreachable on {host}: {type(exc).__name__}: {exc}')
        return False

    if _SOURCE_ID not in status:
        print(f'[ FAIL ] Snapserver serves {sorted(status)}, with no {_SOURCE_ID} stream — is the source enabled?')
        return False

    # `idle` is the expected state, since nothing is sending. Only registration is checkable here.
    print(f'[  OK  ] Snapserver has the {_SOURCE_ID} stream ({status[_SOURCE_ID]})')
    return True


async def _run(args: argparse.Namespace) -> int:
    """Runs the discovery and stream checks and returns the process exit status."""
    name = _airplay_receiver_name()
    target = 'the network' if args.scan else args.host

    print(f'>>> Looking for AirPlay receiver {name!r} on {target}')
    config = await _find_receiver(None if args.scan else args.host, name, args.timeout)
    if config is None:
        print(f'[ FAIL ] No AirPlay receiver found. Is the AirPlay source enabled and snapserver running on {args.host}?')
        return 1
    print(f'[  OK  ] Found {config.name!r} at {config.address}')

    advertised = _check_advertisement(config)
    registered = await _check_stream(args.host)

    if not (advertised and registered):
        return 1

    print(f'[  OK  ] {name!r} is advertising AirPlay 2 and Snapserver is ready to ingest it')
    print('         Playing audio is not checkable from here — send to it from an iPhone, iPad, or Mac.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default=os.getenv('AUDERA_SNAPSERVER_HOST'), help="the streamer's address")
    parser.add_argument('--scan', action='store_true', help='sweep the network with multicast instead of probing --host')
    parser.add_argument('--timeout', type=float, default=5.0, help='discovery timeout (default: 5)')
    args = parser.parse_args()

    if not args.host:
        parser.error('pass --host, or set AUDERA_SNAPSERVER_HOST in .env')

    try:
        import pyatv  # noqa: F401  # ty: ignore[unresolved-import]
    except ImportError:
        parser.error('pyatv is not installed — run this with `uv run --with pyatv python ...`')

    return asyncio.run(_run(args))


if __name__ == '__main__':
    sys.exit(main())
