"""Cached environment/deployment settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven deployment settings, loaded once at startup.

    Every field is overridable via an `AUDERA_`-prefixed environment variable
    (or a matching key in a local `.env` file); the defaults reproduce the
    values that were previously hardcoded across the package.

    Attributes
    ----------
    snapserver_host: `str`
        The hostname or IP address of the Snapserver instance.
    plexamp_host: `str`
        The hostname or IP address of the PlexAmp headless instance.
    snapserver_port: `int`
        The Snapserver HTTP/JSON-RPC WebSocket port.
    camilladsp_port: `int`
        The CamillaDSP WebSocket port.
    plexamp_port: `int`
        The PlexAmp headless HTTP port.
    server_host: `str`
        The interface the web UI binds to.
    server_port: `int`
        The port the web UI binds to.
    """

    model_config = SettingsConfigDict(env_prefix='AUDERA_', env_file='.env', extra='ignore')

    # Hosts (backend services)
    snapserver_host: str = 'localhost'
    plexamp_host: str = 'localhost'

    # Service ports
    snapserver_port: int = 1780
    camilladsp_port: int = 1234
    plexamp_port: int = 32500

    # Web UI bind
    server_host: str = '0.0.0.0'
    server_port: int = 80


settings = Settings()
