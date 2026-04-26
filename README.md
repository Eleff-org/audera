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
| **Snapserver / Snapclient** | Synchronized multi-room audio distribution | 1704 (audio), 1705 (JSON-RPC WS) |
| **CamillaDSP** | Per-device DSP pipeline (EQ, room correction) | 1234 (WebSocket) |

### Devices

**Server** — one per system (or zone)
- Runs Plex-Amp (headless), Snapserver, Snapclient, and CamillaDSP
- Hosts the Audera webserver at `https://audera.local` — manages volume and mute for all connected players
- CamillaDSP sits in the Snapclient audio path so each device DSPs independently

**Player** — one per room
- Runs Snapclient and CamillaDSP
- Connects to the server automatically on boot; managed via the server webserver
- No local webserver required

## Installation

Audera is designed for [DietPi](https://dietpi.com/) on Raspberry Pi hardware. Setup scripts are provided for both device types.

### Server

1. Flash DietPi to an SD card and copy `os/dietpi/streamer/dietpi.txt` to the boot partition.
2. Boot the device and SSH in as `root`.
3. Run the setup script, optionally passing a branch name (defaults to `main`):

   ```bash
   sudo bash os/dietpi/streamer/automation/setup.sh [branch]
   ```

### Player

1. Flash DietPi to an SD card and copy `os/dietpi/player/dietpi.txt` to the boot partition.
2. Boot the device and SSH in as `root`.
3. Run the setup script, optionally passing a branch name (defaults to `main`):

   ```bash
   sudo bash os/dietpi/player/automation/setup.sh [branch]
   ```

## Development

`audera` supports Python >= 3.11. To install from source:

```bash
git clone -b main https://github.com/Eleff-org/audera.git
cd audera
pip install -e .
```

## Roadmap

See [PROJECT.md](./PROJECT.md) for current status, planned workstreams, and release milestones.
