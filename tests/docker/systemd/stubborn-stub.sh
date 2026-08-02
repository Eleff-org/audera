#!/bin/bash
# A backend that ignores SIGTERM, so systemd escalates to SIGKILL after TimeoutStopSec. Against a
# unit like this, `systemctl disable --now` blocks for the manager's default 90 s stop timeout while
# `system.TIMEOUT` is 15 s, and the seam catches only `CalledProcessError`, so
# `subprocess.TimeoutExpired` propagates, the Sources tab's `except Exception` fires, and
# `systemctl restart snapserver` is skipped, leaving the rendered conf and the running server
# divergent.
#
# Swapped into a unit's ExecStart by drop-in for that one test. Nothing enables it by default.
trap '' TERM INT

sleep infinity &
wait
