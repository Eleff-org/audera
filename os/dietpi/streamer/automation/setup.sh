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

# Variables
GIT_REPO_URL="https://github.com/Eleff-org/audera.git"
CAMILLADSP_VERSION="3.0.1"
CAMILLADSP_ARCHIVE="camilladsp-linux-aarch64.tar.gz"
CAMILLADSP_URL="https://github.com/HEnquist/camilladsp/releases/download/v${CAMILLADSP_VERSION}/${CAMILLADSP_ARCHIVE}"
CAMILLADSP_CONFIG_DIR="/etc/camilladsp"
CAMILLADSP_CONFIG="$CAMILLADSP_CONFIG_DIR/config.yml"
CAMILLADSP_STATEFILE="$CAMILLADSP_CONFIG_DIR/state.yml"

SNAPSERVER_CONFIG="/etc/snapserver.conf"
ASOUND_CONFIG="/etc/asound.conf"


# Start console logging

print_logo
echo
echo ">>> Running the Audera streamer setup & installation..."
echo
echo "    Script source {https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/streamer/automation/setup.sh}."

# Ensure the script is running as root
require_root

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
    snapserver \
    snapclient \
    python3.13 \
    python3-dev \
    build-essential \
    jq && \
apt-get clean && \
rm -rf /var/lib/apt/lists/*
echo -e "[  ${GREEN}OK${RESET}  ] Packages installed successfully"

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

# Install audera CLI
echo
echo ">>> Installing audera"
install_audera_cli "$GIT_REPO_URL" "$GIT_BRANCH"
echo -e "[  ${GREEN}OK${RESET}  ] audera installed successfully"

# Write Snapserver configuration
echo
echo ">>> Creating the Snapserver configuration"
audera streamer conf snapserver.conf > "$SNAPSERVER_CONFIG"
chmod 644 "$SNAPSERVER_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] Snapserver configured successfully"

# Write CamillaDSP configuration
echo
echo ">>> Creating the CamillaDSP configuration"
audera streamer conf camilladsp.yml > "$CAMILLADSP_CONFIG"
chmod 644 "$CAMILLADSP_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] CamillaDSP configured successfully"

# Create plexamp-mdns helper
echo
echo ">>> Creating plexamp-mdns helper"
cat > /usr/local/bin/plexamp-mdns.sh <<'EOF'
#!/bin/bash
exec avahi-publish -a -R plexamp.local $(hostname -I | awk '{print $1}')
EOF
chmod +x /usr/local/bin/plexamp-mdns.sh
echo -e "[  ${GREEN}OK${RESET}  ] plexamp-mdns helper created"

# Install systemd service units
echo
echo ">>> Installing systemd service units"

# snapserver service
cat > /etc/systemd/system/snapserver.service <<EOF
[Unit]
Description=Snapcast server
After=network.target sound.target

[Service]
ExecStart=/usr/bin/snapserver -c $SNAPSERVER_CONFIG
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# snapclient service — outputs to ALSA loopback; CamillaDSP reads from the paired device
cat > /etc/systemd/system/snapclient.service <<EOF
[Unit]
Description=Snapcast client
Wants=avahi-daemon.service
After=network-online.target time-sync.target sound.target avahi-daemon.service snapserver.service

[Service]
ExecStart=/usr/bin/snapclient --host 127.0.0.1 --soundcard hw:Loopback,0 --sampleformat 48000:32:*
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# camilladsp service — captures from ALSA loopback, plays to physical DAC (hw:0)
write_camilladsp_service "$CAMILLADSP_CONFIG" "$CAMILLADSP_STATEFILE"

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

[Install]
WantedBy=multi-user.target
EOF

# audera-streamer service — long-running NiceGUI UI
cat > /etc/systemd/system/audera-streamer.service <<'EOF'
[Unit]
Description=Audera streamer
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/audera streamer start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable snapserver snapclient camilladsp plexamp plexamp-mdns audera-streamer
systemctl start snapserver snapclient camilladsp plexamp plexamp-mdns audera-streamer
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
