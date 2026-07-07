#!/bin/sh
snapserver --config /etc/snapserver.conf &
sleep 5
while true; do
    snapclient --host 127.0.0.1 --player stdout >/dev/null 2>&1
    sleep 2
done
