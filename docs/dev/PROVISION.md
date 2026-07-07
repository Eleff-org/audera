# Provisioning an Audera Device

`os/dietpi/setup/provision.sh` provisions a streamer or player over SSH by fetching and running the appropriate `setup.sh` from a given Git branch.

## Prerequisites

- Git for Windows installed (provides a bash shell)
- SSH access to the target device (default user: `root`, port: `22`)
- The device is reachable at its IP address

## Setup

Clone the repository and change into the project root:

```powershell
git clone https://github.com/Eleff-org/audera.git
cd audera
```

## Usage

Run the script from the project root using Git's bundled bash.

**Streamer:**

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device streamer --host <IP> --branch <branch>
```

**Player:**

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device player --host <IP> --branch <branch>
```

### Example

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device streamer --host 192.168.1.35 --branch v0.1.0-beta.1
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device player --host 192.168.1.12 --branch v0.1.0-beta.1
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
| `-a, --audio-device` | | Configure `dtoverlay` for the attached audio device: `hdmi`, `digiamp-plus`, `dac-plus`, `hifiberry-dac-plus`. Unset leaves the existing `dtoverlay` untouched. `hdmi` additionally uses firmware-KMS (`dtoverlay=vc4-fkms-v3d`) so the legacy `hdmi_*` settings apply, and renders the CamillaDSP playback format as `S16LE` (many HDMI sinks reject `S32LE`). |
| `--no-reboot` | | Skip final reboot; leaves device running for inspection |
| `--wipe-networks` | | Delete all NetworkManager connections before reboot (triggers WiFi wizard on next boot) |
| `--check` | | After reboot, poll until device is reachable then verify systemd services |
| `--check-timeout` | `120` | Seconds to wait for the device to come back after reboot |
| `-l, --log` | | Tee session output to a local file |
| `--dry-run` | | Print the remote command without executing |

## Post-provisioning check

Pass `--check` to have the script wait for the device to come back after reboot and verify that all expected systemd services are active:

```powershell
& "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh --device streamer --host 192.168.1.35 --branch v0.1.0-beta.1 --check
```

Services verified per device type:

- **Streamer:** `snapserver`, `snapclient`, `camilladsp`, `nginx`, `avahi-daemon`
- **Player:** `snapclient`, `camilladsp`
