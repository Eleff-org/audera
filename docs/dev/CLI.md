# Audera CLI Reference

## Streamer

```bash
audera streamer start
```

Starts the streamer. If the device is not connected to a network, runs the Wi-Fi onboarding wizard first (`audera.ui.setup`), then launches the streamer web UI (`audera.ui.streamer.app`).

```bash
audera streamer conf <filename>
```

Prints a bundled streamer config file to stdout. Used during provisioning to write configs to their target paths.

Available files:

| Filename | Written to |
|---|---|
| `snapserver.conf` | `/etc/snapserver.conf` |
| `camilladsp.yml` | `/etc/camilladsp/config.yml` |
| `asound.conf` | `/etc/asound.conf` (appended) |

## Player

```bash
audera player start
```

Starts the player. If the device is not connected to a network, runs the Wi-Fi onboarding wizard first (`audera.ui.setup`). No web UI is started — the player is managed from the streamer.

```bash
audera player conf <filename>
```

Prints a bundled player config file to stdout. Used during provisioning to write configs to their target paths.

Available files:

| Filename | Written to |
|---|---|
| `camilladsp.yml` | `/etc/camilladsp/config.yml` |

## Dispatch

Commands are wired in `audera/cli/audera.py` (argparse) and implemented in `audera/cli/commands.py`. Both subparser levels use `required=True` so missing subjects or verbs produce a clear argparse error.
