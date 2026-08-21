#!/bin/sh
# go-librespot stub, covering conf acceptance and stream registration only, not backend
# behaviour. Ignores argv and writes 44100:16:2 of silence to stdout.
while dd if=/dev/zero bs=17640 count=1 status=none; do sleep 0.1; done
