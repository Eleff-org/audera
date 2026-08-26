#!/bin/bash

# Streamer-only install/setup helpers for Audera device setup scripts.
# Sourced by streamer/automation/setup.sh. The unit files and the plexamp-mdns helper this used to
#   write as heredocs are now rendered by `audera streamer conf <name>` and redirected into place by
#   `setup.sh`; Python is their single source of truth. Only `activate_streamer_units` remains here,
#   because it orchestrates `systemctl` rather than writing a file.

# Reloads systemd and brings the streamer's units to their provisioned state.
activate_streamer_units() {
    systemctl daemon-reload

    # Infrastructure, always on
    systemctl enable snapserver snapclient camilladsp audera-streamer

    # Optional sources. `audera streamer units` derives both lists from `~/.audera/sources.json`,
    #   which survives a reprovision because this script writes only `/etc`, `/var/lib`, and unit
    #   files, falling back to `audera.dal.sources.DEFAULT_ENABLED` on a freshly flashed device. No
    #   source or unit is named here, so changing the bootstrap set or the catalog is a change to
    #   Python alone. The Snapserver conf is rendered from the same record.
    local disabled_units enabled_units
    disabled_units="$(audera streamer units --disabled)"
    enabled_units="$(audera streamer units --enabled)"

    # Unquoted expansions: the output is one unit per line and must word-split into one argument
    #   each. Either list can be empty, and `systemctl enable` with no unit is a usage error, so
    #   each is guarded.
    if [ -n "$disabled_units" ]; then
        # `--now`, matching `toggle.apply`: without it a reprovision leaves the previous image's
        #   backend running, holding its port or fifo, with nothing in the conf naming it.
        # shellcheck disable=SC2086
        systemctl disable --now $disabled_units
    fi
    if [ -n "$enabled_units" ]; then
        # shellcheck disable=SC2086
        systemctl enable $enabled_units
    fi

    # Source units start first and on their own line: snapserver forks shairport-sync, which needs
    # AirPlay's PTP clock already up, and `systemctl start a b` enqueues its jobs concurrently.
    if [ -n "$enabled_units" ]; then
        # shellcheck disable=SC2086
        systemctl start $enabled_units
    fi
    systemctl start snapserver snapclient camilladsp audera-streamer
}
