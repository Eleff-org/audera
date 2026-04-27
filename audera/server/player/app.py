"""Audera player FastAPI server"""

import socket
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

import audera
from audera.dal import identities
from audera.models import identity as identity_models
from audera.services.mdns import PlayerBroadcaster
from audera.services.netifaces import NetworkConnectionError, get_local_ip_address


@asynccontextmanager
async def lifespan(app: FastAPI):
    identity = identities.get_identity()

    # The address may be empty if no network was available during setup; resolve it now.
    if not identity.address:
        try:
            identity = identities.update(
                identity_models.Identity(
                    name=identity.name,
                    uuid=identity.uuid,
                    mac_address=identity.mac_address,
                    address=get_local_ip_address(),
                )
            )
        except NetworkConnectionError:
            pass

    broadcaster = PlayerBroadcaster(identity=identity, port=audera.PLAYER_PORT)
    await broadcaster.async_start()
    yield
    await broadcaster.async_stop()


app = FastAPI(lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/ready')
def ready():
    try:
        with socket.create_connection(('localhost', audera.SNAPCLIENT_PORT), timeout=1.0):
            pass
        return {'status': 'ready'}
    except OSError:
        return JSONResponse(status_code=503, content={'status': 'unavailable'})


@app.get('/identity')
def identity():
    return identities.get_identity().to_dict()


def run():
    """Starts the Audera player FastAPI server."""
    uvicorn.run(
        'audera.server.player.app:app',
        host='0.0.0.0',
        port=audera.PLAYER_PORT,
        log_level='warning',
    )
