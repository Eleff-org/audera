#!/bin/bash
# `audera` on PATH, standing in only for the verbs that would be harmful in a container.
#
# `audera-streamer.service`'s ExecStart is `audera streamer start`, which runs a NiceGUI app and
# `index.adopt_running_sources` in a second process, rewriting the `sources.json` the tests seed. A
# `start` therefore idles, exactly as `idle-stub.sh` does for the four binaries that have no usable
# real implementation here.
#
# Every other verb runs the installed CLI. `lib/streamer.sh`'s `activate_streamer_units` reads
# `audera streamer units --disabled` and `--enabled` to decide the unit state, and provisioning is
# the fixture in this lane, so a stubbed answer there would be the tests asserting against their own
# stub rather than against the catalog and the recorded source set.
if [ "$2" != 'start' ]; then
    exec /app/.venv/bin/audera "$@"
fi

# `sleep infinity &` plus `wait` rather than `exec sleep infinity`, so this script stays the unit's
# MainPID; see `idle-stub.sh`, whose reasoning this half repeats.
trap 'kill %1 2>/dev/null; exit 0' TERM INT

sleep infinity &
wait
