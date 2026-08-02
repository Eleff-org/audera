#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Parse arguments
if [ -n "$1" ]; then
    GIT_BRANCH="$1"
else
    GIT_BRANCH="main"
fi

AUDIO_DEVICE="$2"

# Fetch and load shared config-injection helpers
curl -fsSL "https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/lib/config.sh" -o /tmp/audera_config_lib.sh
source /tmp/audera_config_lib.sh

# Fetch and load shared install/setup helpers
curl -fsSL "https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/lib/common.sh" -o /tmp/audera_common_lib.sh
source /tmp/audera_common_lib.sh

# Fetch and load the streamer-only install/setup helpers
curl -fsSL "https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/lib/streamer.sh" -o /tmp/audera_streamer_lib.sh
source /tmp/audera_streamer_lib.sh

# Variables
GIT_REPO_URL="https://github.com/Eleff-org/audera.git"
CAMILLADSP_VERSION="3.0.1"
CAMILLADSP_CONFIG_DIR="/etc/camilladsp"
CAMILLADSP_CONFIG="$CAMILLADSP_CONFIG_DIR/config.yml"
CAMILLADSP_STATEFILE="$CAMILLADSP_CONFIG_DIR/state.yml"

SNAPSERVER_CONFIG="/etc/snapserver.conf"
SNAPSERVER_HOME="/var/lib/snapserver"
# Must match the `datadir` the rendered snapserver.conf states. Snapserver writes `server.json`
# here, holding the player names, volumes, latencies, groups, and stream assignments Audera
# does not store.
SNAPSERVER_DATADIR="/var/lib/snapserver"
ASOUND_CONFIG="/etc/asound.conf"

GO_LIBRESPOT_VERSION="0.7.4"
GO_LIBRESPOT_ARCHIVE="go-librespot_linux_arm64.tar.gz"
GO_LIBRESPOT_URL="https://github.com/devgianlu/go-librespot/releases/download/v${GO_LIBRESPOT_VERSION}/${GO_LIBRESPOT_ARCHIVE}"
# go-librespot finds this directory by expanding $HOME, which the snapserver unit sets to
# SNAPSERVER_HOME, so the path is derived from SNAPSERVER_HOME.
GO_LIBRESPOT_CONFIG_DIR="$SNAPSERVER_HOME/.config/go-librespot"


# Start console logging

print_logo
echo
echo ">>> Running the Audera streamer setup & installation..."
echo
echo "    Script source {https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/streamer/automation/setup.sh}."

# Ensure the script is running as root
require_root

# Ensure the DietPi apt repository is present
#   `shairport-sync-airplay2` only exists there. Debian trixie's own `shairport-sync 4.3.7-1`
#   is built without `--with-airplay-2`, so an install that falls back to it ships AirPlay 1,
#   which pairs and plays.
echo
echo ">>> Verifying the DietPi apt repository"
if [ ! -f /etc/apt/sources.list.d/dietpi.list ]; then
    echo -e "[  ${RED}FAIL${RESET}  ] Missing {/etc/apt/sources.list.d/dietpi.list}; shairport-sync-airplay2 is unavailable"
    exit 1
fi
echo -e "[  ${GREEN}OK${RESET}  ] DietPi apt repository verified"

# Install build packages
echo
echo ">>> Installing build packages"
apt-get update && \
apt-get install -y \
    wget \
    curl \
    git \
    network-manager \
    dnsmasq \
    alsa-utils \
    avahi-daemon \
    avahi-utils \
    nginx \
    openssl \
    snapserver=0.31.0-1 \
    snapclient \
    shairport-sync-airplay2=4.3.7-dietpi2 \
    python3.13 \
    python3-dev \
    build-essential \
    libsensors5 \
    jq && \
apt-mark hold snapserver shairport-sync-airplay2 && \
apt-get clean && \
rm -rf /var/lib/apt/lists/*
echo -e "[  ${GREEN}OK${RESET}  ] Packages installed successfully"

# Neutralize the packaged shairport-sync daemon
#
#   Snapserver forks its own `/usr/local/bin/shairport-sync` for the `airplay://` source. A
#   standalone daemon competing for RTSP :7000 makes snapserver's forked instance bump its
#   port on every retry and lose its metadata pipe while audio still plays, so nothing
#   surfaces it. Masking the unit leaves the binary alone; snapserver executes it directly,
#   so AirPlay still works. The `apt-mark hold` above covers the upgrade case, where the
#   postinst unmasks and then restarts.
#
#   `nqptp` is left running. The same .deb enabled and started it, and AirPlay is the default
#   source, so it must hold UDP 319/320 before snapserver forks the binary.
echo
echo ">>> Neutralizing the packaged shairport-sync daemon"
systemctl disable --now shairport-sync
systemctl mask shairport-sync
echo -e "[  ${GREEN}OK${RESET}  ] shairport-sync daemon neutralized"

# Load ALSA loopback module (needed for CamillaDSP ↔ Snapclient audio path)
# index=7 keeps the loopback off hw:0 so physical card indices are stable
echo
echo ">>> Enabling ALSA loopback module"
setup_alsa_loopback
echo -e "[  ${GREEN}OK${RESET}  ] ALSA loopback module enabled"

# Configure audio device dtoverlay (opt-in; leaves existing dtoverlay untouched if unset)
echo
configure_audio_device "$AUDIO_DEVICE"

# Install CamillaDSP
echo
echo ">>> Installing CamillaDSP v${CAMILLADSP_VERSION}"
install_camilladsp "$CAMILLADSP_VERSION"
echo -e "[  ${GREEN}OK${RESET}  ] CamillaDSP installed successfully"

# Install uv
echo
echo ">>> Installing uv"
install_uv
echo -e "[  ${GREEN}OK${RESET}  ] uv installed successfully"

# Install Node.js
echo
echo ">>> Installing Node.js"
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
echo -e "[  ${GREEN}OK${RESET}  ] Node.js installed successfully"

echo
echo ">>> Installing PlexAmp headless"
PLEXAMP_URL=$(curl -s "https://plexamp.plex.tv/headless/version.json" | jq -r '.updateUrl')
if [ -z "$PLEXAMP_URL" ] || [ "$PLEXAMP_URL" = "null" ]; then
    echo -e "[  ${RED}FAIL${RESET}  ] Failed to fetch PlexAmp download URL"
    exit 1
fi
wget --show-progress "$PLEXAMP_URL" -O /tmp/plexamp.tar.bz2
tar -xjf /tmp/plexamp.tar.bz2 -C /opt/
rm /tmp/plexamp.tar.bz2
echo -e "[  ${GREEN}OK${RESET}  ] PlexAmp headless installed successfully"

# Install go-librespot
#
#   go-librespot has no apt package, so the release-asset URL is the pin. The tarball is flat,
#   holding the binary and a README at the root, so a single named member extracts into place.
echo
echo ">>> Installing go-librespot v${GO_LIBRESPOT_VERSION}"
wget --show-progress "$GO_LIBRESPOT_URL" -O "/tmp/${GO_LIBRESPOT_ARCHIVE}"
tar -xzf "/tmp/${GO_LIBRESPOT_ARCHIVE}" -C /usr/local/bin go-librespot
chmod +x /usr/local/bin/go-librespot
rm "/tmp/${GO_LIBRESPOT_ARCHIVE}"
echo -e "[  ${GREEN}OK${RESET}  ] go-librespot installed successfully"

# Install audera CLI
echo
echo ">>> Installing audera"
install_audera_cli "$GIT_REPO_URL" "$GIT_BRANCH"
echo -e "[  ${GREEN}OK${RESET}  ] audera installed successfully"

# Write Snapserver configuration
echo
echo ">>> Creating the Snapserver configuration"
#   Rendered to a sibling file and moved into place. `>` truncates the destination before
#   `execve`, so a render that exits non-zero — a `sources.json` naming no catalogued source makes
#   it raise — would leave a zero-byte conf and a Snapserver that will not start, on a device
#   whose previous conf was fine. `set -e` aborts the run before the `mv`.
audera streamer conf snapserver.conf > "${SNAPSERVER_CONFIG}.tmp"
chmod 644 "${SNAPSERVER_CONFIG}.tmp"
mv "${SNAPSERVER_CONFIG}.tmp" "$SNAPSERVER_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] Snapserver configured successfully"

# Write the go-librespot configuration
#
#   Rendered once at provision time and not re-rendered, since snapserver forks and reaps
#   go-librespot itself, so nothing here changes when the Spotify source is toggled. The
#   directory holds the zeroconf credentials that let a re-enable skip re-pairing. No flag
#   points go-librespot at it; it derives `$HOME/.config/go-librespot` on its own, and the
#   snapserver unit's `Environment=HOME` is what makes that path correct.
echo
echo ">>> Creating the go-librespot configuration"
mkdir -p "$GO_LIBRESPOT_CONFIG_DIR"
audera streamer conf go-librespot.yml > "$GO_LIBRESPOT_CONFIG_DIR/config.yml"
chmod 644 "$GO_LIBRESPOT_CONFIG_DIR/config.yml"
echo -e "[  ${GREEN}OK${RESET}  ] go-librespot configured successfully"

# Carry an existing server.json to the datadir the conf now pins
#
#   Two legacy locations, either of which a device may hold depending on when it was last
#   provisioned: `/root/.config/snapserver/` from before the unit set $HOME ($HOME unset, so
#   snapserver fell back to root's passwd entry) and `$SNAPSERVER_HOME/.config/snapserver/`
#   from a device provisioned with $HOME set while `datadir` was still empty.
#
#   The `-e` check on the destination prevents an overwrite: a reprovision of a device already
#   on the pinned path must not take a stale copy from a legacy location. The loop tries the
#   newest layout first and stops at the first match.
echo
echo ">>> Migrating any existing snapserver state"
if [ -e "$SNAPSERVER_DATADIR/server.json" ]; then
    echo -e "[  ${GREEN}OK${RESET}  ] snapserver state already in place, left untouched"
else
    mkdir -p "$SNAPSERVER_DATADIR"
    MIGRATED=""
    for legacy in "$SNAPSERVER_HOME/.config/snapserver/server.json" /root/.config/snapserver/server.json; do
        if [ -f "$legacy" ]; then
            cp "$legacy" "$SNAPSERVER_DATADIR/server.json"
            MIGRATED="$legacy"
            break
        fi
    done
    if [ -n "$MIGRATED" ]; then
        echo -e "[  ${GREEN}OK${RESET}  ] snapserver state migrated from ${MIGRATED}"
    else
        echo -e "[  ${GREEN}OK${RESET}  ] No prior snapserver state to migrate"
    fi
fi

# Write CamillaDSP configuration
echo
echo ">>> Creating the CamillaDSP configuration"
audera streamer conf camilladsp.yml \
    --playback-format "$(camilladsp_playback_format "$AUDIO_DEVICE")" > "$CAMILLADSP_CONFIG"
chmod 644 "$CAMILLADSP_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] CamillaDSP configured successfully"

# Create plexamp-mdns helper
echo
echo ">>> Creating plexamp-mdns helper"
write_plexamp_mdns_helper
echo -e "[  ${GREEN}OK${RESET}  ] plexamp-mdns helper created"

# Install systemd service units
echo
echo ">>> Installing systemd service units"

write_streamer_units "$SNAPSERVER_HOME" "$SNAPSERVER_CONFIG" "$CAMILLADSP_CONFIG" "$CAMILLADSP_STATEFILE"
activate_streamer_units
echo -e "[  ${GREEN}OK${RESET}  ] systemd service units installed successfully"

# Purge ifupdown

# ifupdown will conflict with Network-Manager if
#   both are installed. Comment out all configuration
#   from `/etc/network/interfaces`.

echo
echo ">>> Purging ifupdown"
purge_ifupdown
echo -e "[  ${GREEN}OK${RESET}  ] ifupdown purged successfully"

# Setup network-manager

# Network-manager should manage all network devices,
#   even those configured within `/etc/network/interfaces`.

echo
echo ">>> Setting up network-manager"
setup_network_manager
echo -e "[  ${GREEN}OK${RESET}  ] Network-manager setup successfully"

# Disable WiFi power save globally
disable_wifi_powersave
echo -e "[  ${GREEN}OK${RESET}  ] WiFi power save disabled globally"

# Derive hostname from MAC address
echo
echo ">>> Configuring hostname from MAC address"
NEW_HOSTNAME=$(derive_hostname_from_mac)
sed -i '/^\[server\]/a host-name=audera' /etc/avahi/avahi-daemon.conf
systemctl enable avahi-daemon
systemctl restart avahi-daemon
echo -e "[  ${GREEN}OK${RESET}  ] avahi hostname configured as {audera.local} (system hostname: ${NEW_HOSTNAME})"

# Generate self-signed TLS certificate for audera.local
echo
echo ">>> Generating self-signed TLS certificate"
openssl req -x509 -newkey rsa:2048 \
    -keyout /etc/ssl/private/audera.local.key \
    -out /etc/ssl/certs/audera.local.crt \
    -days 3650 -nodes \
    -subj "/CN=audera.local" \
    -addext "subjectAltName=DNS:audera.local,DNS:plexamp.local"
chmod 600 /etc/ssl/private/audera.local.key
echo -e "[  ${GREEN}OK${RESET}  ] TLS certificate generated"

# Configure nginx reverse proxy
echo
echo ">>> Configuring nginx"
cat > /etc/nginx/sites-available/audera.local <<'EOF'
server {
    listen 443 ssl;
    server_name audera.local;

    ssl_certificate     /etc/ssl/certs/audera.local.crt;
    ssl_certificate_key /etc/ssl/private/audera.local.key;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 443 ssl;
    server_name plexamp.local;

    ssl_certificate     /etc/ssl/certs/audera.local.crt;
    ssl_certificate_key /etc/ssl/private/audera.local.key;

    location / {
        proxy_pass http://127.0.0.1:32500;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
ln -sf /etc/nginx/sites-available/audera.local /etc/nginx/sites-enabled/audera.local
rm -f /etc/nginx/sites-enabled/default
systemctl enable nginx
systemctl restart nginx
echo -e "[  ${GREEN}OK${RESET}  ] nginx configured"

# Setup dnsmasq
echo
echo ">>> Setting up dnsmasq"
systemctl disable dnsmasq
echo -e "[  ${GREEN}OK${RESET}  ] dnsmasq setup successfully"

# Configure alsa
echo
echo ">>> Configuring alsa"
audera streamer conf asound.conf > "$ASOUND_CONFIG"
chmod 644 "$ASOUND_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] alsa configured successfully"

# Write boot banner
echo
echo ">>> Writing boot banner"
write_boot_banner
echo -e "[  ${GREEN}OK${RESET}  ] Boot banner written"

# Log
echo
echo -e "[  ${GREEN}OK${RESET}  ] The Audera streamer setup & installation completed successfully"

# Restart
echo
echo ">>> Restarting the Audera streamer in 5 [sec.] ..."
sleep 5
reboot
