"""Client factories and settings loader shared across the streamer pages."""

import os

import audera
from audera.clients import CamillaDSPClient, SnapserverClient
from audera.dal import settings as settings_dal
from audera.models.settings import Settings
from audera.ui import features


def _load_settings() -> Settings:
    return settings_dal.get_or_create(
        Settings(
            plexamp_host=os.getenv('AUDERA_PLEXAMP_HOST', 'localhost'),
            snapserver_host=os.getenv('AUDERA_SNAPSERVER_HOST', 'localhost'),
            features=features.default_selections(),
        )
    )


def _snapserver(settings: Settings) -> SnapserverClient:
    return SnapserverClient(host=settings.snapserver_host, port=audera.SNAPSERVER_PORT)


def _camilladsp(host: str) -> CamillaDSPClient:
    """Returns a CamillaDSPClient for the given player host."""
    return CamillaDSPClient(host=host)
