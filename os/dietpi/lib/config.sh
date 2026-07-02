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
