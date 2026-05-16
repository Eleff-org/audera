#!/usr/bin/env bash
# Re-provision an Audera device (streamer or player) from a Git branch over SSH.
set -euo pipefail

DEVICE=''
HOST=''
BRANCH='main'
USER='root'
PORT='22'
IDENTITY=''
NO_REBOOT=0
WIPE_NETWORKS=0
CHECK=0
CHECK_TIMEOUT=120
LOG=''
DRY_RUN=0

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
      --no-reboot                  Skip final reboot; leaves device running for inspection
      --wipe-networks              Delete all NM connections before reboot (triggers WiFi wizard on next boot)
      --check                      After reboot, poll until device is reachable then verify systemd services
      --check-timeout <seconds>    Seconds to wait for device to come back after reboot (default: 120)
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
        --no-reboot)         NO_REBOOT=1; shift ;;
        --wipe-networks)     WIPE_NETWORKS=1; shift ;;
        --check)             CHECK=1; shift ;;
        --check-timeout)     CHECK_TIMEOUT="$2"; shift 2 ;;
        -l|--log)            LOG="$2"; shift 2 ;;
        --dry-run)           DRY_RUN=1; shift ;;
        -h|--help)           usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

[[ -n "$DEVICE" ]] || die "--device is required (streamer or player)"
[[ -n "$HOST" ]]   || die "--host is required"
[[ "$DEVICE" == 'streamer' || "$DEVICE" == 'player' ]] || die "--device must be 'streamer' or 'player'"
[[ "$WIPE_NETWORKS" -eq 1 && "$CHECK" -eq 1 ]] && die "--wipe-networks and --check are incompatible (device won't have WiFi after wipe)"

BRANCH_URL="${BRANCH//#/%23}"

SETUP_URL="https://raw.githubusercontent.com/Eleff-org/audera/${BRANCH_URL}/os/dietpi/${DEVICE}/automation/setup.sh"

SED_STRIP="sed -i '/^echo.*Restarting/d; /^sleep 5\$/d; /^[[:space:]]*reboot[[:space:]]*\$/d' /tmp/audera_setup.sh"

FETCH_CMD="curl -fsSL '${SETUP_URL}' -o /tmp/audera_setup.sh"

if [[ "$WIPE_NETWORKS" -eq 1 || "$NO_REBOOT" -eq 1 ]]; then
    SETUP_CMD="${FETCH_CMD} && ${SED_STRIP} && bash /tmp/audera_setup.sh '${BRANCH}'"
else
    SETUP_CMD="${FETCH_CMD} && bash /tmp/audera_setup.sh '${BRANCH}'"
fi

WIPE_CMD="nohup bash -c '
  nmcli -t -f UUID con show | while IFS= read -r uuid; do
    [ -n \"\$uuid\" ] && nmcli con delete uuid \"\$uuid\"
  done
  reboot
' &>/dev/null &"

REBOOT_CMD='reboot'

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
    _log "SSH target : ${USER}@${HOST}:${PORT}"
    _log "Device     : ${DEVICE}"
    _log "Branch     : ${BRANCH}"
    _log "Setup URL  : ${SETUP_URL}"
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

if [[ "$CHECK" -eq 1 && "$NO_REBOOT" -eq 0 ]]; then
    case "$DEVICE" in
        streamer) SERVICES=('snapserver' 'snapclient' 'camilladsp' 'nginx' 'avahi-daemon') ;;
        player)   SERVICES=('snapclient' 'camilladsp') ;;
    esac

    _log "[$(date '+%Y-%m-%d %H:%M:%S')] Waiting for ${HOST} to come back (timeout: ${CHECK_TIMEOUT}s) ..."
    DEADLINE=$(( $(date +%s) + CHECK_TIMEOUT ))
    REACHABLE=0
    while [[ $(date +%s) -lt $DEADLINE ]]; do
        if ssh "${SSH_OPTS[@]}" -o BatchMode=yes "${USER}@${HOST}" true 2>/dev/null; then
            REACHABLE=1
            break
        fi
        sleep 5
    done

    if [[ "$REACHABLE" -eq 0 ]]; then
        die "Device ${HOST} did not come back within ${CHECK_TIMEOUT}s."
    fi

    _log "[$(date '+%Y-%m-%d %H:%M:%S')] Device is reachable. Checking services ..."
    FAILED=()
    for svc in "${SERVICES[@]}"; do
        STATUS=$(_ssh systemctl is-active "$svc" 2>/dev/null || true)
        if [[ "$STATUS" == 'active' ]]; then
            _log "  [OK]   ${svc}"
        else
            _log "  [FAIL] ${svc} (${STATUS})"
            FAILED+=("$svc")
        fi
    done

    if [[ "${#FAILED[@]}" -gt 0 ]]; then
        die "Services not active: ${FAILED[*]}"
    fi

    _log "[$(date '+%Y-%m-%d %H:%M:%S')] All services active. Re-provisioning complete."
else
    _log "[$(date '+%Y-%m-%d %H:%M:%S')] Re-provisioning complete."
fi
