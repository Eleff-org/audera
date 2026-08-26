FROM debian:trixie-slim

# Real systemd as PID 1, so `enable --now` and `disable --now` have observable effects. The code
# under test runs in here and a host-side driver `docker exec`s it; a job-level `container:` on a
# hosted runner overrides the entrypoint, which would keep systemd from being PID 1.
ENV container=docker
ENV DEBIAN_FRONTEND=noninteractive

# `systemd-sysv` for `/sbin/init`, `dbus` because systemctl talks to the manager over it, `procps`
# for the `ps` the leak probes read, `socat` for the PlexAmp stub's listener, `git` for the
# `camilladsp-plot` git dependency, and `gcc`/`libc6-dev` because `netifaces` is sdist-only and
# compiles at install time.
#
# `iproute2` is deliberately absent, so there is no `ss`. Probe a port with a Python socket connect,
# as `_plex._plexamp_state` does; the package would give the tests a probe the code under test does
# not have.
#
# `snapserver=0.31.0-1` is what the device runs, as in `tests/docker/snapserver/Dockerfile`. The
# behaviours under test here (`default_source` reassignment, backends re-forked on stdout EOF) are
# version-specific. `snapclient` is pinned to the same version and moved aside below; the unit still
# runs a stub.
RUN apt-get update -qq \
    && apt-get install -y \
       --no-install-recommends \
       -o Dpkg::Options::=--force-confold \
       systemd systemd-sysv dbus \
       procps socat git ca-certificates \
       gcc libc6-dev \
       snapserver=0.31.0-1 snapclient=0.31.0-1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# The Debian package enables its own `snapserver.service` in `postinst`, which would start a
# snapserver from the packaged conf at container boot, before provisioning writes Audera's unit over
# it. Removing the symlink disables the unit; `streamer.sh`'s `activate_streamer_units()` recreates
# it.
RUN rm -f /etc/systemd/system/multi-user.target.wants/snapserver.service

# The real snapclient is moved off the path `snapclient.service` names, so the provisioned unit gets
# the idle stub copied below. Only `tests/systemd/inside/conftest.py`'s `listening_player` runs this
# binary, directly rather than under a unit.
#
# The package's own unit is deleted along with its symlink: `/usr/lib/systemd/system/
# snapclient.service` would answer `systemctl show` for a unit
# `tests/systemd/inside/test_provisioning.py` removes and expects to read as `not-found`.
RUN mv /usr/bin/snapclient /usr/local/bin/snapclient-real \
    && rm -f /usr/lib/systemd/system/snapclient.service \
             /etc/systemd/system/multi-user.target.wants/snapclient.service

# `platform.NAME` is computed at import from this file, via `dotenv.load_dotenv`. A real file makes
# the `@platform.requires('dietpi')` gate pass without a patch. The version numbers are arbitrary;
# the key names and the shape are DietPi's.
COPY tests/docker/systemd/dietpi.version /boot/dietpi/.version

# Units the device gets from apt rather than from Audera, so they must exist before provisioning can
# enable them. `nqptp.service` ships inside DietPi's `shairport-sync-airplay2`, from a DietPi-only
# repo; `avahi-daemon.service` is `plexamp-mdns.service`'s `Requires=`, and a missing `Requires=`
# fails the start of the unit under test. Both go in `/usr/lib/systemd/system/`, where a package
# would put them, which keeps `/etc/systemd/system/` exclusively Audera's and lets a drop-in
# override them.
COPY tests/docker/systemd/nqptp.service /usr/lib/systemd/system/nqptp.service
COPY tests/docker/systemd/avahi-daemon.service /usr/lib/systemd/system/avahi-daemon.service

# A unit that fails on its own terms, so the seam's `CalledProcessError` path is driven by systemd's
# refusal.
COPY tests/docker/systemd/audera-test-failing.service /usr/lib/systemd/system/audera-test-failing.service

# Stubs at the paths the catalog's URIs and the provisioned units already name, so neither is
# rewritten for the container. The two shared with `tests/docker/snapserver/` are copied from there
# rather than duplicated.
COPY tests/docker/snapserver/go-librespot-stub.sh /usr/local/bin/go-librespot
COPY tests/docker/snapserver/shairport-sync-stub.sh /usr/local/bin/shairport-sync

# `idle-stub.sh` stands in at four paths. `nqptp` and `avahi-publish` have DietPi-only binaries.
# `snapclient` and `camilladsp` would interfere with the tests: a real snapclient restart-loops
# against a `hw:Loopback,0` no container has and settles `failed`.
COPY tests/docker/systemd/idle-stub.sh /usr/local/bin/nqptp
COPY tests/docker/systemd/idle-stub.sh /usr/local/bin/avahi-publish
COPY tests/docker/systemd/idle-stub.sh /usr/bin/snapclient
COPY tests/docker/systemd/idle-stub.sh /usr/local/bin/camilladsp

# `audera` is half a stub: `streamer start` idles, every other verb runs the installed CLI, which
# `activate_streamer_units` reads to decide the unit state. See the script.
COPY tests/docker/systemd/audera-stub.sh /usr/local/bin/audera

# Swapped into a unit's `ExecStart` by drop-in for the wedged-backend test only. It ignores
# SIGTERM, so systemd has to escalate to SIGKILL, which is the escalation `TimeoutStopSec` bounds.
COPY tests/docker/systemd/stubborn-stub.sh /usr/local/bin/stubborn-backend

COPY tests/docker/systemd/plexamp-node-stub.sh /usr/bin/node

RUN chmod +x \
      /usr/local/bin/go-librespot /usr/local/bin/shairport-sync \
      /usr/local/bin/nqptp /usr/local/bin/avahi-publish /usr/bin/snapclient \
      /usr/local/bin/camilladsp /usr/local/bin/audera \
      /usr/local/bin/stubborn-backend /usr/bin/node

# systemd refuses to start a unit whose `WorkingDirectory` is missing, and `plexamp.service`
# declares `WorkingDirectory=/opt/plexamp`, so the tree exists even though the stub at
# `/usr/bin/node` never reads the script.
RUN mkdir -p /opt/plexamp/js && : > /opt/plexamp/js/index.js

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /usr/local/bin/

ENV HOME=/root
WORKDIR /app

# Dependencies before source, so editing a test rebuilds the last two layers rather than
# recompiling `netifaces` and re-cloning `camilladsp-plot`. A bind mount is not used because the
# repo lives on a mapped drive, which Docker Desktop mounts unreliably.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --all-extras --no-install-project

# Provisioning is the fixture here: the image ships no Audera unit files, and `provision()` renders
# them from `audera.cli.conf` and shells to `streamer.sh`'s `activate_streamer_units` to enable them.
# `streamer.sh` is named one by one rather than copying `lib/`, which would pull in `config.sh` silently.
COPY audera ./audera
# `brand/tokens.css` and `brand/fonts` are `force-include`d into the wheel by pyproject.toml, so the
# project install below fails to build without them.
COPY brand ./brand
COPY tests ./tests
COPY os/dietpi/lib/streamer.sh ./os/dietpi/lib/streamer.sh

# Installs the project, which `_plex.py` needs: it calls `importlib.metadata.version('audera')` at
# module scope, so the UI import fails outright against a venv that only has the dependencies.
RUN uv sync --frozen --all-extras

# The repo-root `.env` names a real streamer on the developer's LAN and `pydantic-settings` reads it
# from the working directory at import. The root `.dockerignore` keeps it out of the context, and an
# `ENV` beats a `.env` entry that reaches the image anyway.
ENV AUDERA_SNAPSERVER_HOST=127.0.0.1
ENV AUDERA_PLEXAMP_HOST=127.0.0.1
ENV AUDERA_SERVER_HOST=127.0.0.1

# Read by `tests/systemd/conftest.py`, which makes `inside/` uncollectable unless it is set, so
# `uv run pytest -m systemd` at the repo root runs the driver only. `docker exec` inherits the
# container's environment, so this reaches the inner pytest without the driver passing it.
ENV AUDERA_IN_SYSTEMD_CONTAINER=1

ENTRYPOINT ["/lib/systemd/systemd"]
