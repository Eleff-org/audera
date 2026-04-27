# Audera

## What is Audera?

`Audera` is a new era of composable audio systems that brings open-protocols to your own hardware for multi-room synchronous playback.

---

## Architecture

Audera is built on top of three best-in-class open-source services rather than implementing custom audio transport or sync:

| Service | Role | Port |
|---|---|---|
| **Plex-Amp** (headless) | Music source / playback queue | 32500 (HTTP) |
| **Snapserver / Snapclient** | Synchronized multi-room audio distribution | 1704 (audio), 1705 (JSON-RPC WS) |
| **CamillaDSP** | Per-device DSP pipeline (EQ, crossover, room correction) | 1234 (WebSocket) |

### Device roles

**Server** — one per system
- Runs Plex-Amp (headless), Snapserver, Snapclient, CamillaDSP
- CamillaDSP sits in the Snapclient audio path only — each device DSPs independently; the Snapserver broadcast is unprocessed
- Hosts the single Audera webserver (NiceGUI, port 80) — controls both the server and all connected players
- Webserver provides: Players view (per-Snapclient volume/mute, including the server itself)
- Reverse-proxied at `https://audera.local` via nginx + avahi-daemon
- Runs the WiFi onboarding wizard on first boot if not connected

**Player** — one per room
- Runs Snapclient and CamillaDSP
- CamillaDSP sits in the Snapclient audio path; volume controlled remotely via the server webserver through the Snapserver JSON-RPC API
- No local webserver — all management is via the server webserver
- Runs the WiFi onboarding wizard on first boot if not connected

### Python package layout

List @./audera/ for the Python package layout.


### OS / DietPi layout

List @./os/dietpi/ for the OS automation scripts.

---

## Migration History

### Pre-migration (≤ v0.11.0): Custom streaming daemon

The original Audera used a fully custom audio transport stack:

- **PyAudio** for audio capture (streamer) and playback (player)
- **TCP sockets** on ports 5000 (audio) and 5001 (latency ping)
- **Zeroconf / mDNS** (`_audera._tcp.local.`) for streamer/player auto-discovery
- **ntplib** for NTP-based clock alignment across devices
- **AirPlay 2** via `shairport-sync-airplay2` as the audio source on the streamer
- **Async orchestrator** pattern (`services/orchestrator.py`) for concurrency
- Models: `Identity`, `Player`, `Session`, `Audio`
- DAL modules: `identities`, `players`, `devices`, `sessions`, `interfaces`
- CLI: `audera run streamer | player`

### Migration (v0.1.0-beta.1): Third-party service stack

The migration replaced the entire custom transport with Snapcast + Plex-Amp + CamillaDSP:

**Deleted:**
- `audera/streamer.py`, `audera/player.py`
- `audera/services/{orchestrator,mdns,ntp,media,sessions,devices}.py`
- `audera/models/{audio,session}.py`
- `audera/dal/{interfaces,devices,sessions}.py`
- `os/dietpi/player/conf/shairport-sync.conf`
- Dependencies: `pyaudio`, `ntplib`, `zeroconf`

**Added:**
- `audera/models/{stream,dsp}.py`
- `audera/dal/{streams,dsp}.py`
- `audera/services/{snapserver,camilladsp,plexamp}.py`
- `audera/server/streamer/app.py`, `audera/server/player/app.py`
- `os/dietpi/streamer/` (entire new directory)
- `os/dietpi/player/conf/camilladsp.yml`
- Dependencies: `httpx`, `websockets`, `pyyaml`

**Reworked:**
- `audera/models/player.py` — `Player` now maps to Snapcast client fields; `Group` maps to Snapcast group fields
- `audera/dal/players.py`, `dal/groups.py` — aligned DTYPES and queries to new models
- `audera/cli/commands.py` — removed asyncio; dispatches to NiceGUI server apps
- `audera/cli/audera.py` — choices: `streamer-server | player-server | player-setup`
- `os/dietpi/player/automation/setup.sh` — replaced shairport-sync with snapclient + camilladsp + systemd units

---

## Current Status

**Branch:** `v0.1.0-beta.1`

| Area | Status |
|---|---|
| Models (`player`, `group`, `stream`, `dsp`) | Complete |
| DAL (`players`, `groups`, `streams`, `dsp`) | Complete |
| Service clients (`snapserver`, `camilladsp`, `plexamp`) | Complete — not yet integration-tested |
| Server webserver — Players tab (`server/streamer/app.py`) | Complete — per-client volume/mute via Snapserver JSON-RPC |
| Player webserver (`server/player/app.py`) | Complete — lightweight FastAPI server (`/health`, `/ready`, `/identity`) with mDNS broadcast on startup |
| WiFi onboarding wizard — player (`ui/player/setup.py`) | Complete — audited; supports both `player` and `streamer` roles |
| WiFi onboarding wizard — server | Complete — `commands.py` checks connectivity and launches wizard with `role='streamer'` before starting server |
| CLI (`audera run streamer-server / player-server / player-setup`) | Complete |
| nginx reverse proxy + avahi (`audera.local`) | Complete — `avahi-daemon` configured with hostname `audera`; self-signed TLS cert generated; nginx reverse-proxies `https://audera.local:443` → `http://localhost:80` with WebSocket upgrade headers |
| DietPi server OS scripts | Complete — `snapclient` included; systemd units for `snapserver`, `snapclient`, `camilladsp` registered; not yet tested on device |
| DietPi player OS scripts | Complete — `snapclient` + `camilladsp` systemd units registered; not yet tested on device |
| mDNS discovery (`services/mdns.py`) | Complete — `PlayerBroadcaster` (player startup) and `PlayerDiscovery` (server-side); test coverage added |
| SSH test harness | Not started |
| Integration test (server ↔ player via Snapcast) | Not started |

---

## Releases

### v0.1.0-beta.1 (current, unreleased)
First release of the third-party service stack. Replaces the custom streaming daemon with Snapcast + Plex-Amp + CamillaDSP. Python application layer reworked to model the new service landscape. DietPi OS setup scripts added for both streamer and player devices.

### v0.11.0 (prior release)
Final release of the custom streaming daemon. Added async orchestrator, shairport-sync AirPlay 2 support, and async-to-sync conversion.

---

## Planned Workstreams

The guiding principle is **simplicity first, ship incrementally**. Each workstream targets a shippable state. Deferred workstreams are listed at the bottom and are explicitly out of scope for v0.1.0.

| Workstream | Description | Status |
|---|---|---|
| WS-1: Server device MVP | DietPi `setup.sh` for server: `snapclient` + `snapserver` + CamillaDSP systemd units; correct ALSA loopback audio path | ✓ Complete |
| WS-2: Server webserver — Players tab | Per-client volume/mute via Snapserver JSON-RPC; nginx reverse proxy + avahi at `audera.local`; self-signed TLS | ✓ Complete |
| WS-3: Player device MVP | DietPi `setup.sh` for player: `snapclient` + CamillaDSP systemd units; lightweight FastAPI player webserver (`/health`, `/ready`, `/identity`) | ✓ Complete |
| WS-4: WiFi onboarding wizard | `ui/player/setup.py` supports both `player` and `streamer` roles; connectivity check on server and player startup | ✓ Complete |

### WS-5: SSH test harness
- Write a shell script (`os/test/reprovision.sh`) that SSHes into a target device and re-runs the appropriate `setup.sh` without a full SD card re-flash
- Parameterize by device type (`server` / `player`) and target IP
- Document the re-provisioning workflow for development iteration

### WS-6: Integration testing
- Provision a server device using `os/dietpi/streamer/dietpi.txt` + `setup.sh` end-to-end; confirm all systemd units start (`snapserver`, `snapclient`, `camilladsp`, `audera-streamer-server`)
- Provision a player device; confirm `snapclient` + `camilladsp` start and the player connects to the server
- Verify the server webserver at `https://audera.local` shows the player in the Players tab
- Verify per-client volume control works end-to-end
- Verify the WiFi onboarding wizard runs correctly on first boot for both device types

### WS-7: Release v0.1.0
- Pass WS-6 integration tests
- `flake8` — zero errors
- Merge `v0.1.0-beta.1` → `main`
- Tag `v0.1.0`
- Update `README.md` with installation steps and architecture overview

---

## Deferred Workstreams

These are explicitly out of scope for v0.1.0 and will be planned in future milestones.

| Workstream | Description |
|---|---|
| Plex-Amp integration | "What's playing" view, transport controls (play/pause/skip), `machine_id` discovery |
| Player groups | Snapcast group/stream assignment, group volume control |
| CamillaDSP pipeline editor | YAML-based filter/pipeline editor in the webserver |
| Other audio sources | AirPlay 2 (shairport-sync), Spotify Connect |
| Debian package distribution | Systemd service units packaged as `.deb` for non-DietPi installs |
| Multiple servers (multi-zone) | Unique per-server mDNS hostnames; configurable server hostname in player `setup.sh`; each server manages its own independent pool of players |

---

## Development Notes

- All config files persist to `~/.audera/{players,groups,streams,dsp}/{id}.json`
- DSP config uses plain `json` (not `pytensils`) because the CamillaDSP pipeline dict cannot be validated against a flat DTYPES schema
- `SnapserverClient` opens a new WebSocket connection per call (stateless) — suitable for low-frequency UI polling; revisit if real-time push is needed
- CamillaDSP pipeline YAML is stored as a `dict` in `DSPConfig.pipeline`; the player webserver round-trips it through `pyyaml` for display and editing
- `Player.group_id` and `Group.stream_id` are empty strings (not `None`) when unassigned, to satisfy the `pytensils` DTYPES `'str'` constraint
