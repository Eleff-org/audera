"""audera

🔮 `audera` is a new era of composable audio systems that brings
open-protocols to your own hardware for multi-room synchronous playback.
"""

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

NAME: str = 'audera'
DESCRIPTION: str = ''.join(
    [
        '🔮 `audera` is a new era of composable audio systems that brings',
        ' open-protocols to your own hardware for multi-room synchronous playback.',
    ]
)

# Websites
HOME: str = 'https://github.com/Eleff-org/audera'

# Service ports
SNAPSERVER_PORT: int = 1780
CAMILLADSP_PORT: int = 1234
PLEXAMP_PORT: int = 32500
SERVER_PORT: int = 80
