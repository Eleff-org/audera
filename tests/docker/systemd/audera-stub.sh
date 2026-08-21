#!/bin/bash
# `audera` on PATH, stubbing only `streamer start`, whose NiceGUI app runs
# `index.adopt_running_sources` in a second process and rewrites the `sources.json` the tests seed.
# It idles instead, as `idle-stub.sh` does.
#
# Every other verb runs the installed CLI, so `activate_streamer_units`'s reads of
# `audera streamer units --disabled` / `--enabled` come from the real catalog and recorded source
# set.
if [ "$2" != 'start' ]; then
    exec /app/.venv/bin/audera "$@"
fi

# `sleep infinity &` plus `wait` rather than `exec sleep infinity`, so this script stays the unit's
# MainPID; see `idle-stub.sh`.
trap 'kill %1 2>/dev/null; exit 0' TERM INT

sleep infinity &
wait
