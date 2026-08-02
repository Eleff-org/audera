#!/bin/bash
# A daemon that stays up and stops cleanly on SIGTERM. Stands in for five binaries the
# provisioned units name, either because the real one is DietPi-only (nqptp, avahi-publish) or
# because the real one is harmful in a container (snapclient, camilladsp, audera).
#
# `sleep infinity &` plus `wait` rather than `exec sleep infinity`, so this script stays the unit's
# MainPID. A leak probe that finds a surviving process can then attribute it to the unit whose
# ExecStart named this path; an `exec` would leave a bare `sleep` that says nothing about which
# unit failed to stop.
#
# It handles SIGTERM, so it is the control against `stubborn-stub.sh` and a TimeoutStopSec
# assertion measures the escalation rather than the ordinary path.
trap 'kill %1 2>/dev/null; exit 0' TERM INT

sleep infinity &
wait
