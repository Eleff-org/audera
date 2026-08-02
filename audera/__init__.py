"""audera

🔮 `audera` is a new era of composable audio systems that brings
open-protocols to your own hardware for multi-room synchronous playback.
"""

from audera import dal, models
from audera.services import ap, logging, netifaces, platform, system
from audera.settings import settings

__all__ = [
    'platform',
    'ap',
    'netifaces',
    'models',
    'dal',
    'logging',
    'system',
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

# Service ports (sourced from the cached environment-settings singleton so the
#   `audera.*_PORT` call sites stay unchanged while becoming env-overridable)
SNAPSERVER_PORT: int = settings.snapserver_port
CAMILLADSP_PORT: int = settings.camilladsp_port
PLEXAMP_PORT: int = settings.plexamp_port
SERVER_PORT: int = settings.server_port
