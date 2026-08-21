#!/bin/bash
# A daemon that stays up and stops cleanly on SIGTERM. Stands in for five binaries the provisioned
# units name, either DietPi-only (nqptp, avahi-publish) or harmful in a container (snapclient,
# camilladsp, audera).
#
# `sleep infinity &` plus `wait` rather than `exec sleep infinity`, so this script stays the unit's
# MainPID and a leak probe can attribute a surviving process to the unit whose ExecStart named this
# path.
#
# Handling SIGTERM makes this the control against `stubborn-stub.sh`.
trap 'kill %1 2>/dev/null; exit 0' TERM INT

sleep infinity &
wait
