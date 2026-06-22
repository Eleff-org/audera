#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Import DietPi global functions
# source "/boot/dietpi/func/dietpi-globals"

# Setup color formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
RESET='\033[0m'

# Parse arguments
if [ -n "$1" ]; then
    GIT_BRANCH="$1"
else
    GIT_BRANCH="main"
fi

# Variables
GIT_REPO_URL="https://github.com/Eleff-org/audera.git"
CAMILLADSP_VERSION="3.0.1"
CAMILLADSP_ARCHIVE="camilladsp-linux-aarch64.tar.gz"
CAMILLADSP_URL="https://github.com/HEnquist/camilladsp/releases/download/v${CAMILLADSP_VERSION}/${CAMILLADSP_ARCHIVE}"
CAMILLADSP_CONFIG_DIR="/etc/camilladsp"
CAMILLADSP_CONFIG="$CAMILLADSP_CONFIG_DIR/config.yml"
CAMILLADSP_STATEFILE="$CAMILLADSP_CONFIG_DIR/state.yml"


# Start console logging

# The logo must be wrapped in single quotes ' ' to avoid escaping characters
#   due to the nature of having double backslashes, like '\\' in the logo

echo ' ________  ___  ___  ________  _______  ________  ________      '
echo '|\   __  \|\  \|\  \|\   ___ \|\   ___\|\   __  \|\   __  \     '
echo '\ \  \|\  \ \  \\\  \ \  \_|\ \ \  \__|\ \  \|\  \ \  \|\  \    '
echo ' \ \   __  \ \  \\\  \ \  \ \\ \ \   __\\ \      /\ \   __  \   '
echo '  \ \  \ \  \ \  \\\  \ \  \_\\ \ \  \_|_\ \  \  \ \ \  \ \  \  '
echo '   \ \__\ \__\ \______/\ \______/\ \______\ \__\\ _\\ \__\ \__\ '
echo '    \|__|\|__|\|______| \|______| \|______|\|__|\|__|\|__|\|__| '
echo
echo ">>> Running the Audera player setup & installation..."
echo
echo "    Script source {https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/player/automation/setup.sh}."

# Ensure the script is running as root
echo
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}*** CRITICAL: The setup-script must be run as {sudo}.${RESET}"
    exit 1
fi

# Install build packages
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
echo "options snd-aloop index=7" > /etc/modprobe.d/snd-aloop.conf
echo "snd-aloop" > /etc/modules-load.d/snd-aloop.conf
modprobe snd-aloop
echo -e "[  ${GREEN}OK${RESET}  ] ALSA loopback module enabled"

# Install CamillaDSP
echo
echo ">>> Installing CamillaDSP v${CAMILLADSP_VERSION}"
wget -q "$CAMILLADSP_URL" -O "/tmp/${CAMILLADSP_ARCHIVE}"
tar -xzf "/tmp/${CAMILLADSP_ARCHIVE}" -C /usr/local/bin/
chmod +x /usr/local/bin/camilladsp
rm "/tmp/${CAMILLADSP_ARCHIVE}"
mkdir -p "$CAMILLADSP_CONFIG_DIR"
echo -e "[  ${GREEN}OK${RESET}  ] CamillaDSP installed successfully"

# Install uv
echo
echo ">>> Installing uv"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
fi
echo -e "[  ${GREEN}OK${RESET}  ] uv installed successfully"

# Install audera CLI
echo
echo ">>> Installing audera"
UV_TOOL_BIN_DIR=/usr/local/bin uv tool install --reinstall "git+${GIT_REPO_URL}@${GIT_BRANCH}"
export PATH="/usr/local/bin:$PATH"
echo -e "[  ${GREEN}OK${RESET}  ] audera installed successfully"

# Write CamillaDSP configuration
echo
echo ">>> Creating the CamillaDSP configuration"
audera player conf camilladsp.yml > "$CAMILLADSP_CONFIG"
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
cat > /etc/systemd/system/camilladsp.service <<EOF
[Unit]
Description=CamillaDSP
After=sound.target snapclient.service

[Service]
ExecStart=/usr/local/bin/camilladsp $CAMILLADSP_CONFIG --statefile $CAMILLADSP_STATEFILE -p 1234 --address 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

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

# Configure os
# echo
# echo ">>> Configuring the operating-system"
# echo ">>> Ensuring wifi availability without hdmi-output"
# G_CONFIG_INJECT 'hdmi_force_hotplug=' 'hdmi_force_hotplug=1' /boot/config.txt
# G_CONFIG_INJECT 'hdmi_drive=' 'hdmi_drive=2' /boot/config.txt
# echo -e "[  ${GREEN}OK${RESET}  ] os configured successfully"

# Purge ifupdown

# ifupdown will conflict with Network-Manager if
#   both are installed. Comment out all configuration
#   from `/etc/network/interfaces`.

echo
echo ">>> Purging ifupdown"

if systemctl is-active --quiet ifupdown; then
    systemctl stop ifupdown
    systemctl disable ifupdown
fi

apt-get purge -y ifupdown
sed -i '/^[[:space:]]*[^#[:space:]]/s/^/# /' /etc/network/interfaces
echo -e "[  ${GREEN}OK${RESET}  ] ifupdown purged successfully"

# Derive hostname from MAC address
echo
echo ">>> Configuring hostname from MAC address"
MAC=$(cat /sys/class/net/eth0/address 2>/dev/null || cat /sys/class/net/wlan0/address)
SHORT=$(echo "$MAC" | tr -d ':' | tail -c 7)
NEW_HOSTNAME="audera-${SHORT}"
hostnamectl set-hostname "$NEW_HOSTNAME"
echo "127.0.1.1   $NEW_HOSTNAME" >> /etc/hosts
echo -e "[  ${GREEN}OK${RESET}  ] Hostname configured as {${NEW_HOSTNAME}}"

# Setup network-manager

# Network-manager should manage all network devices,
#   even those configured within `/etc/network/interfaces`.

echo
echo ">>> Setting up network-manager"
sed -i '/^\[ifupdown\]/,/^\[/s/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf
systemctl enable NetworkManager
systemctl start NetworkManager
nmcli networking on
echo -e "[  ${GREEN}OK${RESET}  ] Network-manager setup successfully"

# Disable WiFi power save globally
echo
echo ">>> Disabling WiFi power save"
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/wifi-powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF
echo -e "[  ${GREEN}OK${RESET}  ] WiFi power save disabled globally"

# Setup dnsmasq
echo
echo ">>> Setting up dnsmasq"
systemctl disable dnsmasq
echo -e "[  ${GREEN}OK${RESET}  ] dnsmasq setup successfully"

# Log
echo
echo -e "[  ${GREEN}OK${RESET}  ] The Audera player setup & installation completed successfully"

# Restart
echo ">>> Restarting the Audera player in 5 [sec.] ..."
sleep 5
reboot
