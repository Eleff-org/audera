"""audera

🔮 `audera` is a new era of composable audio systems that brings
open-protocols to your own hardware for multi-room synchronous playback.
"""

from typing import List

from audera import dal, models
from audera.services import ap, logging, netifaces, platform

__all__ = [
    'platform',
    'ap',
    'netifaces',
    'models',
    'dal',
    'logging',
]

# Logo
LOGO: List[str] = [
    r' ________  ___  ___  ________  _______  ________  ________      ',
    r'|\   __  \|\  \|\  \|\   ___ \|\   ___\|\   __  \|\   __  \     ',
    r'\ \  \|\  \ \  \\\  \ \  \_|\ \ \  \__|\ \  \|\  \ \  \|\  \    ',
    r' \ \   __  \ \  \\\  \ \  \ \\ \ \   __\\ \      /\ \   __  \   ',
    r'  \ \  \ \  \ \  \\\  \ \  \_\\ \ \  \_|_\ \  \  \ \ \  \ \  \  ',
    r'   \ \__\ \__\ \______/\ \______/\ \______\ \__\\ _\\ \__\ \__\ ',
    r'    \|__|\|__|\|______| \|______| \|______|\|__|\|__|\|__|\|__| ',
]
NAME: str = 'audera'
DESCRIPTION: str = ''.join(
    [
        '🔮 `audera` is a new era of composable audio systems that brings',
        ' open-protocols to your own hardware for multi-room synchronous playback.',
    ]
)

# Websites
HOME: str = 'https://github.com/Eleff-org/audera'
DOCS: str = 'https://github.com/Eleff-org/audera/tree/main/docs'

# Service ports
SNAPSERVER_PORT: int = 1780
SNAPCLIENT_PORT: int = 1704
CAMILLADSP_PORT: int = 1234
PLEXAMP_PORT: int = 32500
SERVER_PORT: int = 80
PLAYER_PORT: int = 8080
