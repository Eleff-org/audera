#!/bin/bash

# Streamer-only install/setup helpers for Audera device setup scripts.
# Sourced by streamer/automation/setup.sh alongside lib/common.sh: `write_streamer_units` calls its
#   `write_camilladsp_service`. Bash resolves function names at call time, so the two `source` lines
#   have no required order.

# Writes the helper `plexamp-mdns.service` executes, which publishes `plexamp.local` over mDNS.
#   Written here, beside the unit that names it, since `_enable_source(PlexAmp)` runs
#   `enable --now plexamp-mdns` and that fails without the ExecStart target present.
write_plexamp_mdns_helper() {
    cat > /usr/local/bin/plexamp-mdns.sh <<'EOF'
#!/bin/bash
exec avahi-publish -a -R plexamp.local $(hostname -I | awk '{print $1}')
EOF
    chmod +x /usr/local/bin/plexamp-mdns.sh
}

# Writes every systemd unit the streamer runs, except `camilladsp.service`, which comes from
#   `lib/common.sh` since the player installs the same unit.
#
# The snapserver and snapclient heredocs are unquoted, so `$snapserver_home` and
#   `$snapserver_config` expand from these locals. `plexamp.service`'s is quoted, so the literal
#   `$(seq 1 30)` and `$i` in its ExecStartPre reach the unit file unexpanded.
#
# Every unit carries TimeoutStopSec=5. Audera stops these units through
#   `audera/services/system.py`, whose subprocess timeout is 15 seconds; the manager's default stop
#   timeout of 90 would let `systemctl` outlive the seam and raise `TimeoutExpired`. A restart is
#   stop-then-start on one budget, hence 5 rather than a value nearer 15.
write_streamer_units() {
    local snapserver_home="$1"
    local snapserver_config="$2"
    local camilladsp_config="$3"
    local camilladsp_statefile="$4"

    # snapserver service
    cat > /etc/systemd/system/snapserver.service <<EOF
[Unit]
Description=Snapcast server
# nqptp because snapserver forks shairport-sync for the airplay:// source, and that fork
#   needs the PTP clock already holding UDP 319/320. After= on a disabled unit is a no-op.
After=network.target sound.target nqptp.service

[Service]
# systemd sets no HOME for a unit with no User=, and everything snapserver forks inherits that.
#   go-librespot exits before flag.Parse computing its --config_dir default via Go's
#   os.UserConfigDir(), which errors when neither XDG_CONFIG_HOME nor HOME is set, so
#   --config_dir does not help. Snapserver then re-forks the dead backend on stdout EOF with no
#   backoff, roughly ten times a second and never reaping, until the device runs out of PIDs.
#   HOME satisfies both branches of os.UserConfigDir() and HOME/.config/go-librespot is where
#   this script rendered config.yml.
# Snapserver reads HOME too: its datadir defaults to HOME/.config/snapserver/ in the foreground,
#   so this line would move server.json, which holds every player name, volume, latency, group,
#   and stream assignment. The rendered conf states datadir outright, which prevents it.
Environment=HOME=$snapserver_home
ExecStart=/usr/bin/snapserver -c $snapserver_config
Restart=on-failure
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

    # snapclient service: outputs to ALSA loopback; CamillaDSP reads from the paired device
    cat > /etc/systemd/system/snapclient.service <<EOF
[Unit]
Description=Snapcast client
Wants=avahi-daemon.service
After=network-online.target time-sync.target sound.target avahi-daemon.service snapserver.service

[Service]
ExecStart=/usr/bin/snapclient --host 127.0.0.1 --soundcard hw:Loopback,0 --sampleformat 48000:32:*
Restart=on-failure
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

    # camilladsp service: captures from ALSA loopback, plays to physical DAC (hw:0)
    write_camilladsp_service "$camilladsp_config" "$camilladsp_statefile"

    # Create PlexAmp data directories
    mkdir -p /root/.local/share/Plexamp/Offline
    mkdir -p /root/.local/share/Plexamp/Settings
    mkdir -p /root/.cache/Plexamp/log

    # Pre-configure PlexAmp audio device to route through snapfifo pipe
    echo -n "Splexamp_output" > "/root/.local/share/Plexamp/Settings/%40Plexamp%3Asettings%3AaudioDeviceUuid"

    # plexamp service
    cat > /etc/systemd/system/plexamp.service <<'EOF'
[Unit]
Description=PlexAmp Headless
After=network-online.target nss-lookup.target
Wants=network-online.target nss-lookup.target

[Service]
Environment=HOME=/root
WorkingDirectory=/opt/plexamp
ExecStartPre=/bin/bash -c 'for i in $(seq 1 30); do getent hosts plex.tv > /dev/null 2>&1 && break || sleep 2; done'
ExecStart=/bin/bash -c 'export CLIENT_NAME=Audera; exec /usr/bin/node /opt/plexamp/js/index.js'
Restart=on-failure
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

    # plexamp-mdns service
    cat > /etc/systemd/system/plexamp-mdns.service <<'EOF'
[Unit]
Description=Publish plexamp.local mDNS hostname
After=avahi-daemon.service network-online.target
Requires=avahi-daemon.service

[Service]
ExecStart=/usr/local/bin/plexamp-mdns.sh
Restart=on-failure
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

    # audera-streamer service: long-running NiceGUI UI
    cat > /etc/systemd/system/audera-streamer.service <<'EOF'
[Unit]
Description=Audera streamer
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/audera streamer start
Restart=on-failure
RestartSec=5
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

    # nqptp stop-timeout drop-in
    #
    # `nqptp.service` ships with DietPi's `shairport-sync-airplay2` package, so this is a drop-in
    #   rather than a unit the script owns and apt would replace. It needs the same stop budget as
    #   the units above: toggling AirPlay from the Sources tab runs `disable --now nqptp`.
    mkdir -p /etc/systemd/system/nqptp.service.d
    cat > /etc/systemd/system/nqptp.service.d/timeout.conf <<'EOF'
[Service]
TimeoutStopSec=5
EOF
}

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
