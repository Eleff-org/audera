# Getting started

To get started with **Audera**, you will need a `Raspberry Pi` device, an audio system with a free `HDMI` or `RCA` input or a spare set of stereo speakers (the old set in your basement would work great!), and a compatible source device or music library to cast into the **Audera** ecosystem.

> [!NOTE]
> We recommend starting with a **Streamer** first. The Streamer acts as both the hub / control plane for any connected **Player** and as a player itself.

## Devices

**Audera** consists of two types of devices, a **Streamer** (one per household) and a **Player** (multiple per household). The **Streamer** hosts a local web app for managing devices (incl. latency adjustment), sources (`AirPlay 2`, `Spotify Connect`, and `Plexamp`), player groups and streams, and per-player DSP pipelines.

## Selecting hardware

**Audera** runs on `Raspberry Pi` devices with [DietPi OS](https://dietpi.com/), and requires the latest stable build of the "Trixie" distribution of `DietPi OS`.

We recommend any of the [Raspberry Pi 4B](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) or [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/) models (1 GB of RAM is enough) for a **Streamer**, and the [Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) for a **Player**.

Depending on the audio system you want to integrate **Audera** with, you may need additional hardware:

- For an audio receiver with a spare `HDMI` input, use the onboard `HDMI0` output of the `Raspberry Pi` device.
- For an audio amplifier with a spare `RCA` input, add a [Raspberry Pi DAC+](https://www.raspberrypi.com/products/dac-plus/) or [HiFiBerry DAC+](https://www.hifiberry.com/shop/boards/hifiberry-dacplus-rca-version/).
- For a spare set of passive stereo speakers, add a [Raspberry Pi DigiAMP+](https://www.raspberrypi.com/products/digiamp-plus/).

## Provisioning

> [!NOTE]
> For a complete guide to provisioning, see the [provisioning docs](dev/PROVISION.md).

1. Flash an SD card with the latest `DietPi OS` for your `Raspberry Pi` device. The official [Raspberry Pi Imager](https://www.raspberrypi.com/software/) supports `DietPi OS` natively. In **Choose OS**, select **Other general-purpose OS**, then scroll down and select **DietPi**.
2. Complete the first-boot process on your `Raspberry Pi` device. You will likely need to set up Wi-Fi credentials, pick your locale, and select your keyboard layout. You do not need to install any additional software during the first boot.
3. Once the first boot completes, run `hostname -I` and record the local IP address of your device.
4. On a separate computer, clone **Audera** locally with `git clone https://github.com/Eleff-org/audera.git`.
5. Navigate into the cloned repository and run the provisioning script for your operating system. Set `--device` to `streamer` or `player`, `--host` to the IP address you recorded, and `--audio-device` to match your hardware (`hdmi`, `digiamp-plus`, `dac-plus`, or `hifiberry-dac-plus`). Optionally add `--hostname <name>` to give the device a friendly name that shows in your router and becomes the setup-hotspot network name (see the [provisioning docs](dev/PROVISION.md) for the full options reference).

    **macOS / Linux**

    ```bash
    bash os/dietpi/setup/provision.sh \
      --device streamer \
      --host <IP> \
      --audio-device hdmi \
      --hostname <name>   # optional
    ```

    **Windows (PowerShell)**

    ```powershell
    & "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe" os/dietpi/setup/provision.sh `
      --device streamer `
      --host <IP> `
      --audio-device hdmi `
      --hostname <name>   # optional
    ```

6. After provisioning completes, the `Raspberry Pi` device restarts into **Wi-Fi Setup** mode.
7. On your phone, open your **Wi-Fi** settings and scan until you see a new network named after the `--hostname` you set (or `audera-{unique-identifier}`, where the unique-identifier is a short string of letters and numbers, when you didn't set one).
8. Select the network. On most phones the setup page opens automatically once you join; if it doesn't, open `10.42.0.1` in a web browser.
9. Complete the **Wi-Fi Setup** steps.
10. Once you finish **Wi-Fi Setup**, the `Raspberry Pi` device restarts.
11. If you set up a **Streamer**, open your Streamer web app at `audera.local` in a browser on any device connected to the same network. If you set up a **Player**, open your Streamer web app and refresh the players tab until the new **Player** appears.
