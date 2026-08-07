# ADR 001: Raspberry Pi Hardware and Architecture Assumptions

**Date:** 2026-04-23
**Status:** Accepted

## Context

Audera is currently designed and tested exclusively on Raspberry Pi hardware running DietPi. Several layers of the system — OS automation, audio pipeline, and binary distribution — embed assumptions about specific hardware capabilities and the target platform. These assumptions are not enforced by code and will cause silent failures on incompatible hardware.

## Decision

The following assumptions are accepted for the current release. Any work to broaden hardware support must revisit each one explicitly.

### CPU architecture: `aarch64`

`setup.sh` downloads `camilladsp-linux-aarch64.tar.gz`. This binary will not run on `x86_64`, `armv7`, or any other architecture. Changing the target platform requires parameterizing the archive URL or distributing CamillaDSP through an alternative mechanism (e.g., a distribution package).

### Soundcard: HiFiBerry DigiAMP+

Both `dietpi.txt` files set `CONFIG_SOUNDCARD=rpi-digiampplus`. This configures DietPi to load the correct ALSA driver for the DigiAMP+ HAT. The physical DAC is addressed as `hw:0,0` (player) and `hw:0` (streamer) in the CamillaDSP config.

Using a different DAC requires:
- Updating `CONFIG_SOUNDCARD` in `dietpi.txt`
- Updating the CamillaDSP `playback.device` in `audera/cli/conf.py` (`render_camilladsp`)
- Verifying the ALSA card index does not shift when `snd-aloop` is loaded at `index=7`

### HDMI audio (Pi 5)

Pi 5 has no `snd_bcm2835`; firmware-KMS (`vc4-fkms-v3d`) binds video-only and enumerates no HDMI audio card. Pi 5 requires full KMS (`vc4-kms-v3d`) for HDMI audio enumeration, and `plughw:0` for playback because the vc4-hdmi ALSA device accepts only `IEC958_SUBFRAME_LE`. Provisioning auto-detects the board model via `/proc/device-tree/model` and applies the correct overlay and playback device. Pi 4 is unaffected — `vc4-fkms-v3d` + `hw:0` remain correct. Non-HDMI DACs are unaffected on both boards.

### OS: DietPi (Debian Trixie, Raspberry Pi OS-based image)

`setup.sh` sources `/boot/dietpi/func/dietpi-globals` for `G_CONFIG_INJECT` and `dietpi-set_hardware`. These functions do not exist on standard Debian or Raspberry Pi OS. The automated first-boot flow (`AUTO_SETUP_*` keys in `dietpi.txt`) is also DietPi-specific.

Packages resolve from two apt origins, Raspberry Pi OS and Debian trixie, so a package name alone does not determine which build is installed. Use `apt-cache policy` to check which origin a given package resolves to.

`snapserver` is pinned to `0.31.0-1` and held (`apt-mark hold`) in `setup.sh`, and the CI testcontainer (`tests/docker/snapserver/Dockerfile`) pins the same version on `debian:trixie-slim`. The Snapcast behaviours Audera's source catalog depends on are version-specific: `default_source` reassignment semantics, the `airplay://` wrapper's forced `44100:16:2`, and the absence of `sandbox_dir` before 0.33.0. The Debian release and the snapserver version are therefore a single assumption. If the version disappears from trixie, the image build and a fresh flash both fail rather than installing a release with different behaviour.

### Network: WiFi only

`dietpi.txt` sets `AUTO_SETUP_NET_ETHERNET_ENABLED=0` and `AUTO_SETUP_NET_WIFI_ENABLED=1`. This is a pre-flash decision. DietPi does not support enabling both simultaneously — if both are set to `1`, WiFi takes priority and Ethernet is disabled.

The player installs NetworkManager post-setup, which can manage additional interfaces (including Ethernet) after first boot. The streamer does not install NetworkManager; its network configuration is fixed at flash time.

## Consequences

- Audera cannot be installed on non-Raspberry Pi hardware without changes to `setup.sh` and the CamillaDSP configs.
- The DigiAMP+ soundcard assumption is not validated at runtime; misconfiguration produces silent audio failure.
- Supporting Ethernet alongside WiFi, or multiple network configurations, requires either a post-flash NetworkManager setup guide or a DietPi preseed alternative.
- Any change to stream format (sample rate, bit depth, channels) must be coordinated across the CamillaDSP config, the Snapclient `--sampleformat` flag, and the Snapserver `source` URI. See ADR 002.
