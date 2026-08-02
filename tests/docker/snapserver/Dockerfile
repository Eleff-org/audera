FROM debian:trixie-slim

# Trixie ships snapcast in main, and 0.31.0-1 is what the device runs (ADR 001). The
# Snapcast behaviours this suite depends on (default_source reassignment, the forced
# airplay:// sampleformat, the absence of sandbox_dir) are version-specific, so an unpinned
# image would test a version the device does not run. Snapclient is pinned too; an unpinned
# client against a pinned server fails at the connect timeout rather than at build time.
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
       --no-install-recommends \
       -o Dpkg::Options::=--force-confold \
       snapserver=0.31.0-1 snapclient=0.31.0-1 \
    && rm -rf /var/lib/apt/lists/*

# Stub source binaries, at the paths the source catalog's URIs name, since snapserver
# refuses to start a process:// or airplay:// stream whose executable is missing. They
# write silence, so the streams run and register. They do not cover go-librespot's Spotify
# session or shairport-sync's option table.
COPY go-librespot-stub.sh /usr/local/bin/go-librespot
COPY shairport-sync-stub.sh /usr/local/bin/shairport-sync
RUN chmod +x /usr/local/bin/go-librespot /usr/local/bin/shairport-sync

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 1780

ENTRYPOINT ["/entrypoint.sh"]
