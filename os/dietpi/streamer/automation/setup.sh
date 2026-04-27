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
CAMILLADSP_VERSION="2.0.3"
CAMILLADSP_ARCHIVE="camilladsp-linux-aarch64.tar.gz"
CAMILLADSP_URL="https://github.com/HEnquist/camilladsp/releases/download/v${CAMILLADSP_VERSION}/${CAMILLADSP_ARCHIVE}"
CAMILLADSP_CONFIG_DIR="/etc/camilladsp"
CAMILLADSP_CONFIG="$CAMILLADSP_CONFIG_DIR/config.yml"

SNAPSERVER_CONFIG="/etc/snapserver.conf"
ASOUND_CONFIG="/etc/asound.conf"

AUTOSTART_DIRECTORY="/var/lib/dietpi/dietpi-autostart"
AUTOSTART_SCRIPT="$AUTOSTART_DIRECTORY/custom.sh"

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
echo ">>> Running the Audera streamer setup & installation..."
echo
echo "    Script source {https://raw.githubusercontent.com/Eleff-org/audera/${GIT_BRANCH}/os/dietpi/streamer/automation/setup.sh}."

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
    nginx \
    openssl \
    snapserver \
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
UV_TOOL_BIN_DIR=/usr/local/bin uv tool install "git+${GIT_REPO_URL}@${GIT_BRANCH}"
echo -e "[  ${GREEN}OK${RESET}  ] audera installed successfully"

# Write Snapserver configuration
echo
echo ">>> Creating the Snapserver configuration"
audera conf streamer snapserver.conf > "$SNAPSERVER_CONFIG"
chmod 644 "$SNAPSERVER_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] Snapserver configured successfully"

# Write ALSA configuration
echo
echo ">>> Installing ALSA configuration"
audera conf streamer asound.conf > "$ASOUND_CONFIG"
chmod 644 "$ASOUND_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] ALSA configured successfully"

# Write CamillaDSP configuration
echo
echo ">>> Creating the CamillaDSP configuration"
audera conf streamer camilladsp.yml > "$CAMILLADSP_CONFIG"
chmod 644 "$CAMILLADSP_CONFIG"
echo -e "[  ${GREEN}OK${RESET}  ] CamillaDSP configured successfully"

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
ExecStart=/usr/local/bin/camilladsp $CAMILLADSP_CONFIG -p 1234
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable snapserver snapclient camilladsp
systemctl start snapserver snapclient camilladsp
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

# Setup network-manager

# Network-manager should manage all network devices,
#   even those configured within `/etc/network/interfaces`.

echo
echo ">>> Setting up network-manager"
sed -i '/^\[ifupdown\]/,/^\[/s/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf
systemctl enable NetworkManager
systemctl restart NetworkManager
nmcli networking on
echo -e "[  ${GREEN}OK${RESET}  ] Network-manager setup successfully"

# Configure avahi hostname
echo
echo ">>> Configuring avahi hostname"
hostnamectl set-hostname audera
systemctl enable avahi-daemon
systemctl restart avahi-daemon
echo -e "[  ${GREEN}OK${RESET}  ] avahi hostname configured as {audera.local}"

# Generate self-signed TLS certificate for audera.local
echo
echo ">>> Generating self-signed TLS certificate"
openssl req -x509 -newkey rsa:2048 \
    -keyout /etc/ssl/private/audera.local.key \
    -out /etc/ssl/certs/audera.local.crt \
    -days 3650 -nodes \
    -subj "/CN=audera.local" \
    -addext "subjectAltName=DNS:audera.local"
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
SOUNDCARD=$(sed -n '/^[[:blank:]]*CONFIG_SOUNDCARD=/{s/^[^=]*=//p;q}' /boot/dietpi.txt)
echo ">>> Assigning {$SOUNDCARD} as the default soundcard"
/boot/dietpi/func/dietpi-set_hardware soundcard $SOUNDCARD
echo -e "[  ${GREEN}OK${RESET}  ] alsa configured successfully"

# Set up the autostart script
echo
echo ">>> Creating the custom autostart script"
mkdir -p "$AUTOSTART_DIRECTORY"
cat > "$AUTOSTART_SCRIPT" <<'EOF'
#!/bin/bash
# DietPi-AutoStart custom script
# Location: /var/lib/dietpi/dietpi-autostart/custom.sh

set -e

exec audera run streamer-server
EOF
chmod +x "$AUTOSTART_SCRIPT"
echo -e "[  ${GREEN}OK${RESET}  ] Custom autostart script created successfully"

# Log
echo
echo -e "[  ${GREEN}OK${RESET}  ] The Audera streamer setup & installation completed successfully"

# Restart
echo ">>> Restarting the Audera streamer in 5 [sec.] ..."
sleep 5
reboot
