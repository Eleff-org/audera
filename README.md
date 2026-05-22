     ________  ___  ___  ________  _______  ________  ________     
    |\   __  \|\  \|\  \|\   ___ \|\   ___\|\   __  \|\   __  \    
    \ \  \|\  \ \  \\\  \ \  \_|\ \ \  \__|\ \  \|\  \ \  \|\  \   
     \ \   __  \ \  \\\  \ \  \ \\ \ \   __\\ \      /\ \   __  \  
      \ \  \ \  \ \  \\\  \ \  \_\\ \ \  \_|_\ \  \  \ \ \  \ \  \ 
       \ \__\ \__\ \______/\ \______/\ \______\ \__\\ _\\ \__\ \__\
        \|__|\|__|\|______| \|______| \|______|\|__|\|__|\|__|\|__|

`Audera` is a new era of composable audio systems that brings open-protocols to your own hardware for multi-room synchronous playback, built on [Plex-Amp](https://www.plex.tv/plexamp/) (headless), [Snapcast](https://github.com/badaix/snapcast), and [CamillaDSP](https://github.com/HEnquist/camilladsp).

## Architecture

| Service | Role | Port |
|---|---|---|
| **Plex-Amp** (headless) | Music source / playback queue | 32500 (HTTP) |
| **Snapserver / Snapclient** | Synchronized multi-room audio distribution | 1704 (audio), 1780 (HTTP API) |
| **CamillaDSP** | Per-device DSP pipeline (EQ, room correction) | 1234 (WebSocket) |

### Devices

**Streamer** — one per system (or zone)
- Runs Plex-Amp (headless), Snapserver, Snapclient, and CamillaDSP
- Hosts the Audera web UI at `https://audera.local` — manages volume and mute for all connected players
- CamillaDSP sits in the Snapclient audio path so each device DSPs independently

**Player** — one per room
- Runs Snapclient and CamillaDSP
- Connects to the streamer automatically on boot; managed via the streamer web UI
- No local web UI required

## Getting started

Audera is designed for [DietPi](https://dietpi.com/) on Raspberry Pi hardware. Devices are provisioned remotely from a host machine using `os/dietpi/setup/provision.sh`.

### 1. Flash DietPi

Flash DietPi to an SD card and copy the appropriate `dietpi.txt` to the boot partition:

- Streamer: `os/dietpi/streamer/dietpi.txt`
- Player: `os/dietpi/player/dietpi.txt`

Boot the device and ensure it is reachable over SSH.

### 2. Provision

Run `provision.sh` from your host machine, pointing it at the target device:

```bash
# Provision a streamer
bash os/dietpi/setup/provision.sh --device streamer --host <IP>

# Provision a player
bash os/dietpi/setup/provision.sh --device player --host <IP>
```

The script fetches and runs the appropriate `setup.sh` on the device over SSH, then reboots it. Once provisioning is complete, the streamer web UI is available at `https://audera.local`.

See [docs/dev/PROVISION.md](docs/dev/PROVISION.md) for the full options reference, examples, and post-provisioning verification.
