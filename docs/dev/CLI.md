# Audera CLI Reference

## Streamer

```bash
audera streamer start
```

Starts the streamer. If the device is not connected to a network, runs the Wi-Fi onboarding wizard first (`audera.ui.setup`), then launches the streamer web UI (`audera.ui.streamer.app`).

```bash
audera streamer conf <filename> [--playback-format {S16LE,S32LE}]
```

Prints a bundled streamer config file (rendered from `audera/cli/conf.py`) to stdout. Used during provisioning to write configs to their target paths.

Available files:

| Filename | Written to |
|---|---|
| `snapserver.conf` | `/etc/snapserver.conf` |
| `camilladsp.yml` | `/etc/camilladsp/config.yml` |
| `asound.conf` | `/etc/asound.conf` (appended) |
| `go-librespot.yml` | `/var/lib/snapserver/.config/go-librespot/config.yml` |

`--playback-format` sets the CamillaDSP playback device format (`camilladsp.yml` only; default `S32LE`). Provisioning passes `S16LE` for `--audio-device hdmi`, which many HDMI sinks require. See ADR 003.

`snapserver.conf` is rendered from `~/.audera/sources.json` (`dal.sources.get_enabled()`), falling back to the bootstrap set (`dal.sources.DEFAULT_ENABLED`) when nothing has been recorded. The file survives a reflash, so a reprovision that emitted the bootstrap set instead would ship a conf naming a stream the operator had turned off and Snapserver would reassign every group onto it at the first client connect.

```bash
audera streamer units (--enabled | --disabled)
```

Prints the systemd units of the enabled audio sources, or of every other catalogued source, one per line in catalog order. Provisioning enables and starts the first list and disables the second, so the unit state of a reprovisioned device follows the same recorded set the conf does, and `os/dietpi/lib/streamer.sh`'s `activate_streamer_units` names no source. A source whose backend Snapserver forks itself has no units and appears in neither list, so either may be empty.

## Player

```bash
audera player start
```

Starts the player. If the device is not connected to a network, runs the Wi-Fi onboarding wizard first (`audera.ui.setup`). No web UI is started — the player is managed from the streamer.

```bash
audera player conf <filename> [--playback-format {S16LE,S32LE}]
```

Prints a bundled player config file (rendered from `audera/cli/conf.py`) to stdout. Used during provisioning to write configs to their target paths.

Available files:

| Filename | Written to |
|---|---|
| `camilladsp.yml` | `/etc/camilladsp/config.yml` |

`--playback-format` sets the CamillaDSP playback device format (`camilladsp.yml` only; default `S32LE`). Provisioning passes `S16LE` for `--audio-device hdmi`, which many HDMI sinks require. See ADR 003.

## Dispatch

Commands are wired in `audera/cli/audera.py` (argparse) and implemented in `audera/cli/commands.py`. Both subparser levels use `required=True` so missing subjects or verbs produce a clear argparse error.
