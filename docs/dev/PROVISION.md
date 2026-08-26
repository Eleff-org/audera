# Provisioning

`os/dietpi/setup/provision.sh` provisions a streamer or player over SSH by fetching and running the appropriate `setup.sh` from a given Git branch.

## Prerequisites

- `bash` (preinstalled on macOS and Linux; on Windows, install [Git for Windows](https://git-scm.com/download/win), which bundles `bash.exe`)
- SSH access to the target device (default user: `root`, port: `22`)
- The device is reachable at its IP address

## Setup

Clone the repository and change into the project root:

```bash
git clone https://github.com/Eleff-org/audera.git
cd audera
```

## Usage

Run the script from the project root. On macOS and Linux, invoke it with your system `bash`; on Windows, invoke it with Git's bundled `bash.exe` from PowerShell.

### Streamer

**macOS / Linux**

```bash
bash os/dietpi/setup/provision.sh --device streamer --host <IP> --branch <branch>
```

**Windows (PowerShell)**

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device streamer --host <IP> --branch <branch>
```

### Player

**macOS / Linux**

```bash
bash os/dietpi/setup/provision.sh --device player --host <IP> --branch <branch>
```

**Windows (PowerShell)**

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device player --host <IP> --branch <branch>
```

### Example

Provision a streamer and a player from the `v0.1.0-beta.1` tag, selecting the attached audio device:

**macOS / Linux**

```bash
bash os/dietpi/setup/provision.sh --device streamer --host 192.168.1.35 --branch v0.1.0-beta.1 --audio-device hdmi
bash os/dietpi/setup/provision.sh --device player --host 192.168.1.12 --branch v0.1.0-beta.1 --audio-device digiamp-plus
```

**Windows (PowerShell)**

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device streamer --host 192.168.1.35 --branch v0.1.0-beta.1 --audio-device hdmi
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device player --host 192.168.1.12 --branch v0.1.0-beta.1 --audio-device digiamp-plus
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-d, --device` | *(required)* | `streamer` or `player` |
| `-H, --host` | *(required)* | Device IP address or hostname |
| `-b, --branch` | `main` | Git branch or tag to install from |
| `-u, --user` | `root` | SSH user |
| `-p, --port` | `22` | SSH port |
| `-i, --identity` | | SSH private key file |
| `-a, --audio-device` | | Configure `dtoverlay` for the attached audio device: `hdmi`, `digiamp-plus`, `dac-plus`, `hifiberry-dac-plus`. Unset leaves the existing `dtoverlay` untouched. `hdmi` renders the CamillaDSP playback format as `S16LE` (many HDMI sinks reject `S32LE`). On Pi 4, it uses firmware-KMS (`dtoverlay=vc4-fkms-v3d`) with the legacy `hdmi_*` settings and `hw:0`. On Pi 5, it uses full KMS (`dtoverlay=vc4-kms-v3d`) and `plughw:0` (vc4-hdmi accepts only `IEC958_SUBFRAME_LE`). Board model is auto-detected. |
| `--no-reboot` | | Skip final reboot; leaves device running for inspection |
| `--wipe-networks` | | Delete all NetworkManager connections before reboot (triggers WiFi wizard on next boot) |
| `-l, --log` | | Tee session output to a local file |
| `--dry-run` | | Print the remote command without executing |
