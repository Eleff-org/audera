#!/bin/bash

# Shared install/setup helpers for Audera device setup scripts.
# Sourced by player/automation/setup.sh and streamer/automation/setup.sh.

# Color formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
RESET='\033[0m'

# Prints the Audera ASCII-art logo to the console
# The logo must be wrapped in single quotes ' ' to avoid escaping characters
#   due to the nature of having double backslashes, like '\\' in the logo
print_logo() {
    echo ' ________  ___  ___  ________  _______  ________  ________      '
    echo '|\   __  \|\  \|\  \|\   ___ \|\   ___\|\   __  \|\   __  \     '
    echo '\ \  \|\  \ \  \\\  \ \  \_|\ \ \  \__|\ \  \|\  \ \  \|\  \    '
    echo ' \ \   __  \ \  \\\  \ \  \ \\ \ \   __\\ \      /\ \   __  \   '
    echo '  \ \  \ \  \ \  \\\  \ \  \_\\ \ \  \_|_\ \  \  \ \ \  \ \  \  '
    echo '   \ \__\ \__\ \______/\ \______/\ \______\ \__\\ _\\ \__\ \__\ '
    echo '    \|__|\|__|\|______| \|______| \|______|\|__|\|__|\|__|\|__| '
}

# Ensures the script is running as root
require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}*** CRITICAL: The setup-script must be run as {sudo}.${RESET}"
        exit 1
    fi
}

# Loads the ALSA loopback module (needed for CamillaDSP <-> Snapclient audio path)
# index=7 keeps the loopback off hw:0 so physical card indices are stable
setup_alsa_loopback() {
    echo "options snd-aloop index=7" > /etc/modprobe.d/snd-aloop.conf
    echo "snd-aloop" > /etc/modules-load.d/snd-aloop.conf
    modprobe snd-aloop
}

# Downloads, extracts, and installs the given CamillaDSP version to /usr/local/bin
install_camilladsp() {
    local version="$1"
    local archive="camilladsp-linux-aarch64.tar.gz"
    local url="https://github.com/HEnquist/camilladsp/releases/download/v${version}/${archive}"
    wget -q "$url" -O "/tmp/${archive}"
    tar -xzf "/tmp/${archive}" -C /usr/local/bin/
    chmod +x /usr/local/bin/camilladsp
    rm "/tmp/${archive}"
    mkdir -p /etc/camilladsp
}

# Writes the camilladsp systemd service unit, captures from ALSA loopback, plays to
#   physical DAC (hw:0)
write_camilladsp_service() {
    local config_path="$1"
    local statefile_path="$2"
    cat > /etc/systemd/system/camilladsp.service <<EOF
[Unit]
Description=CamillaDSP
After=sound.target snapclient.service
StartLimitIntervalSec=0

[Service]
ExecStart=/usr/local/bin/camilladsp $config_path --statefile $statefile_path -p 1234 --address 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}

# Installs uv if it is not already present
install_uv() {
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
    fi
}

# Installs the audera CLI from the given git repo/branch
install_audera_cli() {
    local repo_url="$1"
    local branch="$2"
    UV_TOOL_BIN_DIR=/usr/local/bin uv tool install --reinstall "git+${repo_url}@${branch}"
    export PATH="/usr/local/bin:$PATH"
}

# Purges ifupdown, which will conflict with Network-Manager if both are installed,
#   and comments out all configuration from `/etc/network/interfaces`
purge_ifupdown() {
    if systemctl is-active --quiet ifupdown; then
        systemctl stop ifupdown
        systemctl disable ifupdown
    fi
    apt-get purge -y ifupdown
    sed -i '/^[[:space:]]*[^#[:space:]]/s/^/# /' /etc/network/interfaces
}

# Sets up network-manager to manage all network devices, even those configured
#   within `/etc/network/interfaces`
setup_network_manager() {
    sed -i '/^\[ifupdown\]/,/^\[/s/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf
    systemctl enable NetworkManager
    systemctl start NetworkManager
    nmcli networking on
}

# Disables WiFi power save globally
disable_wifi_powersave() {
    mkdir -p /etc/NetworkManager/conf.d
    cat > /etc/NetworkManager/conf.d/wifi-powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF
}

# Derives the hostname from the eth0 (falling back to wlan0) MAC address, sets it,
#   and appends it to /etc/hosts; echoes the derived hostname so the caller can
#   capture it
derive_hostname_from_mac() {
    local mac short new_hostname
    mac=$(cat /sys/class/net/eth0/address 2>/dev/null || cat /sys/class/net/wlan0/address)
    short=$(echo "$mac" | tr -d ':' | tail -c 7)
    new_hostname="audera-${short}"
    hostnamectl set-hostname "$new_hostname"
    echo "127.0.1.1   $new_hostname" >> /etc/hosts
    echo "$new_hostname"
}

# Writes the boot banner printed at login
write_boot_banner() {
    cat > /etc/profile.d/50-audera-banner.sh <<'EOF'
#!/bin/sh
printf '\033[36m'
cat << 'LOGO'
 ________  ___  ___  ________  _______  ________  ________
|\   __  \|\  \|\  \|\   ___ \|\   ___\|\   __  \|\   __  \
\ \  \|\  \ \  \\\  \ \  \_|\ \ \  \__|\ \  \|\  \ \  \|\  \
 \ \   __  \ \  \\\  \ \  \ \\ \ \   __\\ \      /\ \   __  \
  \ \  \ \  \ \  \\\  \ \  \_\\ \ \  \_|_\ \  \  \ \ \  \ \  \
   \ \__\ \__\ \______/\ \______/\ \______\ \__\\ _\\ \__\ \__\
    \|__|\|__|\|______| \|______| \|______|\|__|\|__|\|__|\|__|
LOGO
printf '\033[0m\n'
printf '  \033[1maudera\033[0m — composable audio for your hardware\n\n'
printf '  \033[33m!\033[0m Do not use \033[1mdietpi-config\033[0m to manage WiFi or audio hardware.\n'
printf '    WiFi:   nmcli device wifi connect <SSID> password <PASS>\n'
printf '    Audio:  aplay -l  |  nano /boot/firmware/config.txt\n\n'
EOF
    chmod +x /etc/profile.d/50-audera-banner.sh
}
