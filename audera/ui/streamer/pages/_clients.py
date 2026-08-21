"""Client factories and settings loader shared across the streamer pages."""

import audera
from audera.clients import CamillaDSPClient, SnapserverClient
from audera.dal import settings as settings_dal
from audera.models.settings import Settings
from audera.settings import settings as env
from audera.ui import features


def _load_settings() -> Settings:
    cfg = settings_dal.get_or_create(
        Settings(
            plexamp_host=env.plexamp_host,
            snapserver_host=env.snapserver_host,
            features=features.default_selections(),
        )
    )

    # An explicitly-set `AUDERA_*` host overrides the persisted `settings.json` so the
    #   local-dev override stays reliable even after the file has been written; an unset
    #   var leaves the persisted value untouched (backwards compatible).
    if 'snapserver_host' in env.model_fields_set:
        cfg.snapserver_host = env.snapserver_host
    if 'plexamp_host' in env.model_fields_set:
        cfg.plexamp_host = env.plexamp_host

    return cfg


def _snapserver(settings: Settings) -> SnapserverClient:
    return SnapserverClient(host=settings.snapserver_host, port=audera.SNAPSERVER_PORT)


def _camilladsp(host: str) -> CamillaDSPClient:
    """Returns a CamillaDSPClient for the given player host."""
    return CamillaDSPClient(host=host)
