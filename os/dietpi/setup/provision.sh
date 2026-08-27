#!/usr/bin/env bash
# Provision an Audera device (streamer or player) from a Git branch over SSH.
set -euo pipefail

DEVICE=''
HOST=''
BRANCH='main'
USER='root'
PORT='22'
IDENTITY=''
NO_REBOOT=0
WIPE_NETWORKS=0
LOG=''
DRY_RUN=0
AUDIO_DEVICE=''
HOSTNAME_ARG=''
CARRY_WIFI=0

usage() {
    cat <<EOF
Usage: $(basename "$0") --device <streamer|player> --host <IP> [OPTIONS]

Required:
  -d, --device <streamer|player>   Target device type
  -H, --host <IP|hostname>         Target device IP or hostname

Options:
  -b, --branch <branch>            Git branch or tag to install from (default: main)
  -u, --user <user>                SSH user (default: root)
  -p, --port <port>                SSH port (default: 22)
  -i, --identity <file>            SSH private key file
  -a, --audio-device <value>       Configure dtoverlay for the attached audio device:
                                    hdmi, digiamp-plus, dac-plus, hifiberry-dac-plus
                                    (default: unset, leaves existing dtoverlay untouched)
      --hostname <name>            Friendly hostname (letters, digits, interior hyphens (≤63 chars)); shows in the
                                    router's DHCP record and becomes the setup-hotspot SSID
                                    (default: unset, MAC-derived audera-<6hex>)
      --carry-wifi                 Migrate the WiFi credentials entered at flash time so the
                                    device rejoins its network without the setup wizard
                                    (default: off, device boots into the wizard)
      --no-reboot                  Skip final reboot; leaves device running for inspection
      --wipe-networks              Delete all NM connections before reboot (triggers WiFi wizard on next boot)
  -l, --log <file>                 Tee session output to a local file
      --dry-run                    Print the remote command without executing
  -h, --help                       Show this help message
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--device)         DEVICE="$2"; shift 2 ;;
        -H|--host)           HOST="$2"; shift 2 ;;
        -b|--branch)         BRANCH="$2"; shift 2 ;;
        -u|--user)           USER="$2"; shift 2 ;;
        -p|--port)           PORT="$2"; shift 2 ;;
        -i|--identity)       IDENTITY="$2"; shift 2 ;;
        -a|--audio-device)   AUDIO_DEVICE="$2"; shift 2 ;;
        --hostname)          HOSTNAME_ARG="$2"; shift 2 ;;
        --carry-wifi)        CARRY_WIFI=1; shift ;;
        --no-reboot)         NO_REBOOT=1; shift ;;
        --wipe-networks)     WIPE_NETWORKS=1; shift ;;
        -l|--log)            LOG="$2"; shift 2 ;;
        --dry-run)           DRY_RUN=1; shift ;;
        -h|--help)           usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

[[ -n "$DEVICE" ]] || die "--device is required (streamer or player)"
[[ -n "$HOST" ]]   || die "--host is required"
[[ "$DEVICE" == 'streamer' || "$DEVICE" == 'player' ]] || die "--device must be 'streamer' or 'player'"
if [[ -n "$AUDIO_DEVICE" ]]; then
    case "$AUDIO_DEVICE" in
        hdmi|digiamp-plus|dac-plus|hifiberry-dac-plus) ;;
        *) die "--audio-device must be one of: hdmi, digiamp-plus, dac-plus, hifiberry-dac-plus" ;;
    esac
fi
if [[ -n "$HOSTNAME_ARG" && ! "$HOSTNAME_ARG" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]]; then
    die "--hostname must be 1-63 chars: letters, digits, and interior hyphens (no leading/trailing hyphen)"
fi

BRANCH_URL="${BRANCH//#/%23}"

SETUP_URL="https://raw.githubusercontent.com/Eleff-org/audera/${BRANCH_URL}/os/dietpi/${DEVICE}/automation/setup.sh"

FETCH_CMD="curl -fsSL '${SETUP_URL}' -o /tmp/audera_setup.sh"

# setup.sh's third argument is its reboot flag: 0 for --no-reboot / --wipe-networks (the operator
# wants the device left running for inspection or a network wipe), 1 otherwise.
if [[ "$WIPE_NETWORKS" -eq 1 || "$NO_REBOOT" -eq 1 ]]; then
    REBOOT_FLAG='0'
else
    REBOOT_FLAG='1'
fi

# setup.sh positional contract: $1 branch, $2 audio, $3 reboot, $4 hostname (empty ⇒ MAC),
#   $5 carry-wifi (0/1).
SETUP_CMD="${FETCH_CMD} && bash /tmp/audera_setup.sh '${BRANCH}' '${AUDIO_DEVICE}' '${REBOOT_FLAG}' '${HOSTNAME_ARG}' '${CARRY_WIFI}'"

WIPE_CMD="nohup bash -c '
  nmcli -t -f UUID con show | while IFS= read -r uuid; do
    [ -n \"\$uuid\" ] && nmcli con delete uuid \"\$uuid\"
  done
  reboot
' &>/dev/null &"

SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -p "$PORT")
[[ -n "$IDENTITY" ]] && SSH_OPTS+=(-i "$IDENTITY")

_ssh() {
    ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "$@"
}

_log() {
    if [[ -n "$LOG" ]]; then
        tee -a "$LOG" <<< "$*"
    else
        echo "$*"
    fi
}

if [[ -n "$LOG" ]]; then
    exec > >(tee -a "$LOG") 2>&1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    _log "=== DRY RUN ==="
    _log "SSH target   : ${USER}@${HOST}:${PORT}"
    _log "Device       : ${DEVICE}"
    _log "Branch       : ${BRANCH}"
    _log "Audio device : ${AUDIO_DEVICE:-<unset, leaves existing dtoverlay untouched>}"
    _log "Hostname     : ${HOSTNAME_ARG:-<unset, MAC-derived audera-<6hex>>}"
    _log "Carry WiFi   : ${CARRY_WIFI}"
    _log "Setup URL    : ${SETUP_URL}"
    _log ""
    _log "--- Step 1: setup command ---"
    _log "$SETUP_CMD"
    if [[ "$WIPE_NETWORKS" -eq 1 ]]; then
        _log ""
        _log "--- Step 2: wipe + reboot command ---"
        _log "$WIPE_CMD"
    elif [[ "$NO_REBOOT" -eq 0 ]]; then
        _log ""
        _log "--- (setup.sh handles its own reboot) ---"
    fi
    exit 0
fi

_log "[$(date '+%Y-%m-%d %H:%M:%S')] Starting re-provisioning: device=${DEVICE} host=${HOST} branch=${BRANCH}"

_log "[$(date '+%Y-%m-%d %H:%M:%S')] Running setup.sh on ${HOST} ..."
_ssh "$SETUP_CMD"
_log "[$(date '+%Y-%m-%d %H:%M:%S')] setup.sh completed."

if [[ "$WIPE_NETWORKS" -eq 1 ]]; then
    if [[ "$NO_REBOOT" -eq 1 ]]; then
        _log "[$(date '+%Y-%m-%d %H:%M:%S')] Wiping network connections (no reboot) ..."
        _ssh 'nmcli -t -f UUID con show | while IFS= read -r uuid; do [ -n "$uuid" ] && nmcli con delete uuid "$uuid"; done'
        _log "[$(date '+%Y-%m-%d %H:%M:%S')] Network connections wiped. Device is running for inspection."
    else
        _log "[$(date '+%Y-%m-%d %H:%M:%S')] Wiping network connections and rebooting ..."
        _ssh "$WIPE_CMD" || true
        _log "[$(date '+%Y-%m-%d %H:%M:%S')] Wipe + reboot command issued (SSH may drop — that is expected)."
    fi
elif [[ "$NO_REBOOT" -eq 0 ]]; then
    _log "[$(date '+%Y-%m-%d %H:%M:%S')] (setup.sh triggered its own reboot)"
fi

_log "[$(date '+%Y-%m-%d %H:%M:%S')] Re-provisioning complete."

