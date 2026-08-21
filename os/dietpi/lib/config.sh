#!/bin/bash

# Shared idempotent config-injection helpers for Audera device setup scripts.
# Sourced by player/automation/setup.sh and streamer/automation/setup.sh.

# Idempotently sets a `key=value` line in a config file — replaces an active or
#   commented-out line matching the key, or appends the line if the key is absent
set_config_line() {
    local file="$1"
    local key="$2"
    local line="$3"
    if grep -qE "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${line}|" "$file"
    elif grep -qE "^#[[:space:]]*${key}=" "$file"; then
        sed -i "s|^#[[:space:]]*${key}=.*|${line}|" "$file"
    else
        echo "$line" >> "$file"
    fi
}

# Idempotently sets a `key=value` kernel command-line parameter — replaces an
#   existing occurrence of the key, or appends the parameter if the key is absent
set_cmdline_param() {
    local file="$1"
    local key="$2"
    local param="$3"
    if grep -qE "(^| )${key}=" "$file"; then
        sed -i -E "s/(^| )${key}=[^ ]*/\1${param}/" "$file"
    else
        sed -i "s/\$/ ${param}/" "$file"
    fi
}

# Returns true when the host is a Raspberry Pi 5
is_pi5() {
    grep -q 'Raspberry Pi 5' /proc/device-tree/model 2>/dev/null
}

# Configures /boot/firmware/config.txt (and cmdline.txt, for hdmi) for the given
#   audio device; a no-op (with a message) when $1 is empty
configure_audio_device() {
    local audio_device="$1"
    if [ -z "$audio_device" ]; then
        echo ">>> No --audio-device specified; leaving existing dtoverlay untouched"
        return
    fi
    echo ">>> Configuring audio device: $audio_device"
    case "$audio_device" in
        hdmi)
            if is_pi5; then
                set_config_line /boot/firmware/config.txt 'dtoverlay' 'dtoverlay=vc4-kms-v3d'
                set_config_line /boot/firmware/config.txt 'dtparam=audio' 'dtparam=audio=on'
            else
                set_config_line /boot/firmware/config.txt 'hdmi_force_hotplug' 'hdmi_force_hotplug=1'
                set_config_line /boot/firmware/config.txt 'hdmi_drive' 'hdmi_drive=2'
                set_config_line /boot/firmware/config.txt 'hdmi_force_edid_audio' 'hdmi_force_edid_audio=1'
                set_config_line /boot/firmware/config.txt 'hdmi_group' 'hdmi_group=1'
                set_config_line /boot/firmware/config.txt 'hdmi_mode' 'hdmi_mode=16'
                set_config_line /boot/firmware/config.txt 'dtoverlay' 'dtoverlay=vc4-fkms-v3d'
                set_config_line /boot/firmware/config.txt 'dtparam=audio' 'dtparam=audio=on'
                set_cmdline_param /boot/firmware/cmdline.txt 'vc4\.force_hotplug' 'vc4.force_hotplug=3'
            fi
            ;;
        digiamp-plus)
            set_config_line /boot/firmware/config.txt 'dtoverlay' 'dtoverlay=rpi-digiampplus'
            set_config_line /boot/firmware/config.txt 'dtparam=audio' 'dtparam=audio=off'
            ;;
        dac-plus)
            set_config_line /boot/firmware/config.txt 'dtoverlay' 'dtoverlay=rpi-dacplus'
            set_config_line /boot/firmware/config.txt 'dtparam=audio' 'dtparam=audio=off'
            ;;
        hifiberry-dac-plus)
            set_config_line /boot/firmware/config.txt 'dtoverlay' 'dtoverlay=hifiberry-dacplus'
            set_config_line /boot/firmware/config.txt 'dtparam=audio' 'dtparam=audio=off'
            ;;
        *)
            echo -e "${RED}*** CRITICAL: Unknown --audio-device '${audio_device}'. Valid values: hdmi, digiamp-plus, dac-plus, hifiberry-dac-plus.${RESET}"
            exit 1
            ;;
    esac
    echo -e "[  ${GREEN}OK${RESET}  ] Audio device configured successfully"
}

# Echoes the CamillaDSP playback format for the given audio device: S16LE for hdmi sinks
#   (which reject S32LE), S32LE otherwise
camilladsp_playback_format() {
    if [ "$1" = 'hdmi' ]; then echo 'S16LE'; else echo 'S32LE'; fi
}

# Echoes the CamillaDSP playback ALSA device for the given audio device: plughw:0 for
#   Pi 5 + hdmi (vc4-hdmi accepts only IEC958_SUBFRAME_LE), hw:0 otherwise
camilladsp_playback_device() {
    if [ "$1" = 'hdmi' ] && is_pi5; then echo 'plughw:0'; else echo 'hw:0'; fi
}
