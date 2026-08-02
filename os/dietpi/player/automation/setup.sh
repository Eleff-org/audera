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
CAMILLADSP_CONFIG_DIR="/etc/camilladsp"
CAMILLADSP_CONFIG="$CAMILLADSP_CONFIG_DIR/config.yml"
CAMILLADSP_STATEFILE="$CAMILLADSP_CONFIG_DIR/state.yml"


# Start console logging

print_logo
echo
echo ">>> Running the Audera player setup & installation..."
echo
echo "    Script source {https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/player/automation/setup.sh}."

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
    snapclient \
    python3.13 \
    python3-dev \
    build-essential && \
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

# Install audera CLI
echo
echo ">>> Installing audera"
install_audera_cli "$GIT_REPO_URL" "$GIT_BRANCH"
echo -e "[  ${GREEN}OK${RESET}  ] audera installed successfully"

# Write CamillaDSP configuration
echo
echo ">>> Creating the CamillaDSP configuration"
audera player conf camilladsp.yml \
    --playback-format "$(camilladsp_playback_format "$AUDIO_DEVICE")" > "$CAMILLADSP_CONFIG"
chmod 644 "$CAMILLADSP_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] CamillaDSP configured successfully"

# Install systemd service units
echo
echo ">>> Installing systemd service units"

# snapclient service — outputs to ALSA loopback; CamillaDSP reads from the paired device
cat > /etc/systemd/system/snapclient.service <<EOF
[Unit]
Description=Snapcast client
Wants=avahi-daemon.service
After=network-online.target time-sync.target sound.target avahi-daemon.service

[Service]
ExecStart=/usr/bin/snapclient --soundcard hw:Loopback,0 --sampleformat 48000:32:*
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# camilladsp service — captures from ALSA loopback, plays to physical DAC (hw:0)
write_camilladsp_service "$CAMILLADSP_CONFIG" "$CAMILLADSP_STATEFILE"

# audera-player service — one-shot that starts audera player on boot
cat > /etc/systemd/system/audera-player.service <<'EOF'
[Unit]
Description=Audera player
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/audera player start
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable snapclient camilladsp audera-player
systemctl start snapclient camilladsp audera-player
echo -e "[  ${GREEN}OK${RESET}  ] systemd service units installed successfully"

# Purge ifupdown

# ifupdown will conflict with Network-Manager if
#   both are installed. Comment out all configuration
#   from `/etc/network/interfaces`.

echo
echo ">>> Purging ifupdown"
purge_ifupdown
echo -e "[  ${GREEN}OK${RESET}  ] ifupdown purged successfully"

# Derive hostname from MAC address
echo
echo ">>> Configuring hostname from MAC address"
NEW_HOSTNAME=$(derive_hostname_from_mac)
echo -e "[  ${GREEN}OK${RESET}  ] Hostname configured as {${NEW_HOSTNAME}}"

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

# Setup dnsmasq
echo
echo ">>> Setting up dnsmasq"
systemctl disable dnsmasq
echo -e "[  ${GREEN}OK${RESET}  ] dnsmasq setup successfully"

# Write boot banner
echo
echo ">>> Writing boot banner"
write_boot_banner
echo -e "[  ${GREEN}OK${RESET}  ] Boot banner written"

# Log
echo
echo -e "[  ${GREEN}OK${RESET}  ] The Audera player setup & installation completed successfully"

# Restart
echo
echo ">>> Restarting the Audera player in 5 [sec.] ..."
sleep 5
reboot
