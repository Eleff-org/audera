# os/dietpi/AGENTS.md

The DietPi provisioning layer.

## Layout

- `setup/provision.sh` — operator entry point, run from a workstation over SSH; fetches and runs a device's `setup.sh`, then optionally reboots or wipes networks.
- `streamer/automation/setup.sh`, `player/automation/setup.sh` — the flash scripts, run as root.
- `streamer/dietpi.txt`, `player/dietpi.txt` — DietPi unattended-install answer files.
- `lib/common.sh`, `lib/config.sh` — helpers both `setup.sh` scripts `source`.
- `lib/streamer.sh` — the streamer-only unit-installation helpers; a player must not call them (they would provision it as a streamer). `write_camilladsp_service` stays in `common.sh` because the player calls it directly.

## What is tested

`lib/streamer.sh`'s three unit writers and `common.sh`'s `write_camilladsp_service` are exercised by `tests/systemd/inside/test_provisioning.py`, which provisions a privileged systemd container by invoking exactly those functions and reads the result back off the manager (`uv run pytest -m systemd -v`). Everything else is verified by flashing a device and checking it by hand: the apt block, the pins, the DietPi repo, the `shairport-sync` neutralization, `dietpi.txt`, NetworkManager, the reboot tail, and any Pi-Zero-2-W timing. The installed stubs stand in for backends, so nothing here covers audio, ALSA, sync, or DSP.

## Conventions

- `setup.sh` uses `set -e` only; `provision.sh` uses `set -euo pipefail`.
- Progress is `echo ">>> Gerund phrase"` then `echo -e "[  ${GREEN}OK${RESET}  ] Past-tense phrase"`; failures are `[  ${RED}FAIL${RESET}  ]` then `exit 1`.
- Backticks inside unquoted heredocs (`<<EOF`) are command substitution, so the systemd unit heredocs write comments without them.

## Traps

1. Do not reformat the last three lines of `setup.sh` (`echo … Restarting` / `sleep 5` / `reboot`). `provision.sh`'s `SED_STRIP` deletes them by regex to implement `--no-reboot` / `--wipe-networks`; re-indenting or rewording them reboots a device the operator asked to keep running.
2. The apt block ends with `apt-get clean && rm -rf /var/lib/apt/lists/*`. A package added later needs its own `apt-get update` (a minute on a Pi Zero 2 W); add to the single install at the top instead.
3. Call `lib/`'s functions as bare commands, never in condition context. `set -e` is suppressed inside a function invoked as an `if`/`while` condition or the left of `&&`, so `if write_streamer_units; then` runs on past a failed unit write.

## Pinning

`apt-mark showhold` must list both apt pins. Unpinning does not crash; the device behaves differently and nothing reports it:

| Pin | What breaks if unpinned |
| :--- | :--- |
| `snapserver=0.31.0-1` | conf keys move between releases; the rendered conf is written to 0.31.0's key set. |
| `shairport-sync-airplay2=4.3.7-dietpi2` | 5.x negotiates a different stdout format while snapserver forces 44100:16:2, producing a byte-misaligned stream that plays as noise. |

go-librespot is pinned by its release-asset URL (no apt package), so there is no `apt-mark hold` to audit it against.

## shairport-sync neutralization

The packaged AirPlay-2 daemon must not run: snapserver forks its own `/usr/local/bin/shairport-sync` for `airplay://`, and a second instance competing for RTSP :7000 silently breaks it (rationale commented at the call site). Three layers, each covering a case the others do not: `disable --now`, `mask`, and `apt-mark hold` (the only one that survives an upgrade). `nqptp` stays enabled because it must own UDP 319/320 before snapserver forks.

## Forked-backend environment

`snapserver.service` runs as root with no `User=`, so systemd sets no `$HOME` and every backend snapserver forks inherits that. The unit sets `HOME` and the conf pins `datadir` (both commented in `lib/streamer.sh` / `setup.sh`). Every `process://` source sets `log_stderr=true`: a forked backend has no unit and no `journalctl`, and Snapcast respawns a failed one with no backoff (~10×/s) until PID exhaustion while the UI still reports it healthy, so snapserver's stderr capture is the only host record of the failure.

## Enable vs. start

`enable` starts a unit at boot; `start` runs it now. Infrastructure (`snapserver`, `snapclient`, `camilladsp`, `audera-streamer`) gets both unconditionally. A catalogued source's units follow the operator's recorded set (`activate_streamer_units` derives them from `audera streamer units --disabled/--enabled`; the shell names no source, so changing `DEFAULT_ENABLED` or reordering `CATALOG` needs no shell change). `~/.audera/sources.json` survives a flash because this script writes only `/etc/*`, `/var/lib/*`, and unit files, and must never seed or overwrite it. Two orderings the code does not comment: the apt install sits above every `systemctl start` (binaries exist before anything forks them), and every `audera streamer conf …` render comes after `install_audera_cli`.
