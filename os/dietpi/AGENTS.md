# os/dietpi/AGENTS.md

The DietPi provisioning layer.

## Layout

- `setup/provision.sh` — operator entry point, run from a workstation over SSH; fetches and runs a device's `setup.sh`, then optionally reboots or wipes networks.
- `streamer/automation/setup.sh`, `player/automation/setup.sh` — the flash scripts, run as root.
- `streamer/dietpi.txt`, `player/dietpi.txt` — DietPi unattended-install answer files.
- `lib/common.sh`, `lib/config.sh` — helpers both `setup.sh` scripts `source`. `common.sh` owns `configure_hostname` (operator name, else the MAC-derived `derive_hostname_from_mac` fallback — both echo the applied name) and `migrate_wifi_credentials` (opt-in carry-over of the SSID/PSK from `wpa_supplicant.conf` into a NetworkManager profile; no creds ⇒ notice + `return 0`, so call it bare per Trap #2).
- `lib/streamer.sh` — `activate_streamer_units`, the streamer-only `systemctl` orchestration; a player must not call it (it would provision it as a streamer). The unit and config files it used to write as heredocs now render from `audera.cli.conf`, which both roles redirect into place with `>`.

## What is tested

The units `audera streamer conf` renders and `activate_streamer_units` enables are exercised by `tests/systemd/inside/test_provisioning.py`, which provisions a privileged systemd container — rendering every unit from `audera.cli.conf` and shelling only to `activate_streamer_units` — and reads the result back off the manager (`uv run pytest -m systemd -v`). Everything else is verified by flashing a device and checking it by hand: the apt block, the pins, the DietPi repo, the `shairport-sync` neutralization, `dietpi.txt`, NetworkManager, the reboot tail, and any Pi-Zero-2-W timing. The installed stubs stand in for backends, so nothing here covers audio, ALSA, sync, or DSP.

## Conventions

- `setup.sh` uses `set -e` only; `provision.sh` uses `set -euo pipefail`.
- `setup.sh`'s positional contract is `$1` branch, `$2` audio, `$3` reboot, `$4` hostname (empty ⇒ MAC-derived), `$5` carry-wifi (`0`/`1`). `provision.sh` threads its `--hostname`/`--carry-wifi` flags in as these positional args rather than regex-editing the script.
- Progress is `echo ">>> Gerund phrase"` then `echo -e "[  ${GREEN}OK${RESET}  ] Past-tense phrase"`; failures are `[  ${RED}FAIL${RESET}  ]` then `exit 1`.
- Whole config and unit files are rendered by `audera {streamer,player} conf <name>` and redirected with `>`; the shell writes no file itself except surgical in-place `sed` edits of OS-owned files and the `openssl` TLS keypair. A player can never emit a streamer unit, because the subject (`streamer`/`player`) picks the renderer.

## Traps

1. The apt block ends with `apt-get clean && rm -rf /var/lib/apt/lists/*`. A package added later needs its own `apt-get update` (a minute on a Pi Zero 2 W); add to the single install at the top instead.
2. Call `lib/`'s functions as bare commands, never in condition context. `set -e` is suppressed inside a function invoked as an `if`/`while` condition or the left of `&&`, so `if activate_streamer_units; then` runs on past a failed `systemctl`.

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

`snapserver.service` runs as root with no `User=`, so systemd sets no `$HOME` and every backend snapserver forks inherits that. The unit sets `HOME` and the conf pins `datadir` (both from `SNAPSERVER_HOME` in `audera.cli.conf`, which renders the unit and the conf). Every `process://` source sets `log_stderr=true`: a forked backend has no unit and no `journalctl`, and Snapcast respawns a failed one with no backoff (~10×/s) until PID exhaustion while the UI still reports it healthy, so snapserver's stderr capture is the only host record of the failure.

## Enable vs. start

`enable` starts a unit at boot; `start` runs it now. Infrastructure backends (`snapserver`, `snapclient`, `camilladsp`) get both unconditionally. The role service (`audera-streamer`/`audera-player`) is enabled at flash but started only on the post-provision reboot: it runs the boot-time connectivity gate that launches the interactive WiFi wizard when offline, and starting it mid-flash — before NetworkManager and the WiFi carry-over are configured — drops into the wizard, hanging the player (oneshot `start` blocks) or leaving the streamer stuck in AP mode instead of streaming (`Type=simple` returns but the wizard is up). Enabled, it starts on the reboot with the network up and exits cleanly, which is where the wizard belongs and where no SSH session is stranded. A catalogued source's units follow the operator's recorded set (`activate_streamer_units` derives them from `audera streamer units --disabled/--enabled`; the shell names no source, so changing `DEFAULT_ENABLED` or reordering `CATALOG` needs no shell change). `~/.audera/sources.json` survives a flash because this script writes only `/etc/*`, `/var/lib/*`, and unit files, and must never seed or overwrite it. Two orderings the code does not comment: the apt install sits above every `systemctl start` (binaries exist before anything forks them), and every `audera streamer conf …` render comes after `install_audera_cli`.
