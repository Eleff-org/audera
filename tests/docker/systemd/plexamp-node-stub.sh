#!/bin/bash
# Stands in for `/usr/bin/node` under `plexamp.service`, reproducing the two PlexAmp behaviours
# `_plex`'s chip ladder is built on:
#
#   1. It binds :32500 only once it holds a claim token. A closed port is the only evidence of an
#      unclaimed device, so `_plexamp_state` cannot read a file instead.
#   2. It binds it late. systemd calls the unit active as soon as it forks node, well before node
#      listens; `STARTUP_GRACE` covers that window and the `starting` chip reports it.
#
# PLEXAMP_STUB_DELAY produces window 2 without patching `STARTUP_GRACE`, and it arrives by drop-in.
# PLEXAMP_CLAIM_TOKEN is the name `_plex._restart_plexamp_with_claim` writes.
#
# Nothing else about PlexAmp is modelled: no Plex account, no library, no playback. It never reads
# /opt/plexamp/js/index.js.
sleep "${PLEXAMP_STUB_DELAY:-0}"

if [ -z "$PLEXAMP_CLAIM_TOKEN" ]; then
    # Unclaimed: up, and never listening. Handles SIGTERM so `stop` is still clean.
    trap 'kill %1 2>/dev/null; exit 0' TERM INT
    sleep infinity &
    wait
    exit 0
fi

# `fork` so the port survives being probed; `/dev/null` because `_plexamp_state` asserts on the
# connect succeeding and reads no bytes.
exec socat TCP-LISTEN:32500,reuseaddr,fork /dev/null
