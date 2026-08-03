#!/bin/bash
# A backend that ignores SIGTERM, so systemd escalates to SIGKILL after TimeoutStopSec. Without that
# bound, `systemctl disable --now` blocks for the manager's default 90 s while `system.TIMEOUT` is
# 15 s, and the seam catches only `CalledProcessError`, so `subprocess.TimeoutExpired` propagates and
# `systemctl restart snapserver` is skipped.
#
# Swapped into a unit's ExecStart by drop-in for that one test. Nothing enables it by default.
trap '' TERM INT

sleep infinity &
wait
