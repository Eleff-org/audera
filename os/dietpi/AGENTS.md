# os/dietpi/AGENTS.md

The DietPi provisioning layer: everything that runs on the device rather than in the package.

## What is here

- `setup/provision.sh` — the operator's entry point, run from a workstation over SSH. Fetches and runs a device's `setup.sh`, then optionally reboots or wipes networks.
- `streamer/automation/setup.sh`, `player/automation/setup.sh` — the flash scripts, run as root on the device.
- `streamer/dietpi.txt`, `player/dietpi.txt` — DietPi's unattended-install answer files.
- `lib/common.sh`, `lib/config.sh` — helpers both `setup.sh` scripts `source` after `curl`-ing them from the branch under test.
- `lib/streamer.sh` — the three unit-installation helpers only `streamer/automation/setup.sh` fetches. They write `snapserver.service`, `plexamp.service` and `audera-streamer.service` and shell out to `audera streamer units`, so a player calling one would provision itself as a streamer. `write_camilladsp_service` stays in `common.sh`, since the player calls it directly and `write_streamer_units` calls it too.

## What is CI-exercisable

`lib/streamer.sh`'s three functions are CI-exercisable, and nothing else here is except `common.sh`'s `write_camilladsp_service`, which `write_streamer_units` calls. `write_plexamp_mdns_helper`, `write_streamer_units` and `activate_streamer_units` were extracted out of `streamer/automation/setup.sh` so that a container could call them. `tests/systemd/inside/` boots real systemd as PID 1 in a privileged container that ships **zero** Audera unit files, and its fixture provisions by invoking exactly those three functions with the arguments `setup.sh` passes, so a provisioned device has a single description in this repository. `tests/systemd/inside/test_provisioning.py` then reads the result back off the manager that loaded it. Run it with `uv run pytest -m systemd -v`, which is opt-in and requires Docker.

That covers the artifacts and their systemd state: every unit loads and is owned by the right package, the unit state mirrors `DEFAULT_ENABLED`, the unquoted heredocs still interpolate and `plexamp.service`'s quoted one still does not, the `nqptp` drop-in is merged, the mDNS helper the unit names exists and is executable, and nothing seeds `~/.audera`. `tests/os/test_provisioning.py` adds host-side guards with no container: `bash -n` over every `*.sh` under `os/`, globbed rather than listed so a script added later is parsed too, the condition-context trap below, that `setup.sh` no longer writes units itself, that the three streamer-only writers are in `lib/streamer.sh` and named nowhere in the `common.sh` a player sources, and that each `setup.sh` `curl`s every library whose functions it calls.

Everything else is still verified by flashing a device and checking it by hand: the apt block, the pins, the DietPi repo, the three-layer `shairport-sync` neutralization, `dietpi.txt`, NetworkManager, the reboot tail, `player/`, and any timing that depends on a Pi Zero 2 W rather than an x86 container. The stubs the image installs stand in for backends, so nothing about audio, ALSA, sync or DSP is covered either.

## Conventions

- `setup.sh` uses `set -e` only, without `-u` or `-o pipefail`. `provision.sh` uses `set -euo pipefail`.
- Progress is `echo ">>> Gerund phrase"` then `echo -e "[  ${GREEN}OK${RESET}  ] Past-tense phrase"`. Failures are `[  ${RED}FAIL${RESET}  ]` followed by `exit 1`.
- Backticks inside unquoted heredocs (`<<EOF`) are command substitution, not markdown. The systemd unit heredocs therefore write comments without them.

## Traps

1. Do not reformat the last three lines of `setup.sh` (`echo … Restarting` / `sleep 5` / `reboot`). `provision.sh`'s `SED_STRIP` deletes them textually, by regex, to implement `--no-reboot` and `--wipe-networks`, so re-indenting, re-quoting, or rewording them reboots a device the operator asked to keep running for inspection.
2. The apt block ends with `apt-get clean && rm -rf /var/lib/apt/lists/*`. Any package added later in the file needs its own `apt-get update`, which costs a minute on a Pi Zero 2 W and adds a second failure point. Add to the single install at the top instead.
3. Call `lib/`'s functions as bare commands, never in condition context. `set -e` is suppressed inside a function invoked as the condition of an `if`, a `while`, or the left operand of `&&`, so `if write_streamer_units; then` keeps a script running past unit writes that failed, where the inline heredocs it replaced aborted. The trap is invisible at the call site, so `tests/os/test_provisioning.py` asserts it.

## Pinning policy

Each pin below exists to hold behaviour fixed. Unpinning one does not cause a crash; the device behaves differently and nothing reports the change.

| Pin | Where | What breaks if unpinned |
| :--- | :--- | :--- |
| `snapserver=0.31.0-1` | apt, held | `sandbox_dir` and other conf keys move between releases; the rendered conf is written against 0.31.0's key set. |
| `shairport-sync-airplay2=4.3.7-dietpi2` | apt, held | 5.x negotiates a different stdout format while snapserver's `airplay://` forces 44100:16:2 regardless, producing a byte-misaligned stream that plays as noise instead of raising an error. |
| go-librespot `v0.7.4` | the release-asset URL | Not an apt package, so the URL is the pin. There is no `apt-mark hold` to audit it against. |

`apt-mark showhold` must list both apt pins.

## The AirPlay 2 package and the three-layer neutralization

`shairport-sync-airplay2` comes from DietPi's own repo, so `setup.sh` asserts `/etc/apt/sources.list.d/dietpi.list` exists before the apt block. Debian trixie ships `shairport-sync 4.3.7-1`, built without `--with-airplay-2`. That build carries the same version string, supports AirPlay 1 only, and nothing downstream reports the difference. `nqptp` needs no apt entry of its own, since it is bundled inside the same `.deb`.

The packaged daemon must not run, because snapserver forks its own `/usr/local/bin/shairport-sync` for the `airplay://` source and a second instance competing for RTSP :7000 makes snapserver's fork bump its port and lose its metadata pipe, with audio still playing and nothing reporting the fault. The neutralization is three layers, each covering a case the others do not:

1. `systemctl disable --now shairport-sync` — the postinst already enabled *and started* it.
2. `systemctl mask shairport-sync` — blocks manual starts and dependency-pulled starts.
3. `apt-mark hold shairport-sync-airplay2` — the only layer that survives an upgrade. The postinst unmasks and then restarts, so `mask` alone is not durable, and the hold prevents the upgrade that would undo it.

Masking the unit does not break AirPlay, because snapserver executes the binary directly as a child process and `mask` only redirects the unit to `/dev/null`. `nqptp` is left enabled and running. It is AirPlay's `units` entry and must own UDP 319/320 before snapserver forks.

## Snapserver's forked backends inherit an empty environment

`snapserver.service` declares no `User=`, so it runs as root, and systemd sets no `$HOME` for such a unit. Everything snapserver forks inherits that environment, and a backend that requires a home directory exits rather than degrading.

go-librespot is one such backend. It computes `--config_dir`'s default by calling Go's `os.UserConfigDir()`, which errors when neither `$XDG_CONFIG_HOME` nor `$HOME` is set, and it returns that error before `flag.Parse` runs, so passing `--config_dir` does not avoid it. `setup.sh` puts `Environment=HOME=/var/lib/snapserver` in the `snapserver.service` it writes, which makes `os.UserConfigDir()` resolve to the directory the config was rendered into. The setting goes in the unit rather than a drop-in because Audera owns this unit; `setup.sh` writes `/etc/systemd/system/snapserver.service` itself, which already overrides the packaged one.

Snapserver reads `$HOME` too. `datadir` defaults to `/var/lib/snapserver/` for a daemonized process and to `$HOME/.config/snapserver/` for a foreground one, and this unit is foreground. `server.json` holds the state Audera does not store (player names, volumes, latencies, group membership, and each group's `stream_id`), so setting `$HOME` without pinning `datadir` starts snapserver from an empty state file with every player renamed back to its MAC. The rendered conf therefore states `datadir = /var/lib/snapserver/` outright, and `setup.sh` migrates a `server.json` found at either legacy path (`/root/.config/snapserver/`, from before there was a `$HOME`, and `/var/lib/snapserver/.config/snapserver/`, from after it but before `datadir` was pinned). The migration never overwrites an existing file at the pinned path.

Anything in this unit's environment is shared by snapserver and every backend it forks. A variable added for one is read by the other, and nothing reports the effect.

Snapcast respawns a failed backend with no backoff. `wd_timeout=0` disables only the watchdog; the respawn comes from the stream's stdout reaching EOF, and there is no delay on the retry. A backend that exits immediately is re-forked roughly ten times a second and never reaped. The visible symptom is an accumulation of `<defunct>` children and a journal filling at hundreds of lines a minute, ending in PID exhaustion, while the Sources tab reports the source enabled and healthy.

A `process://` source therefore keeps `log_stderr=true`. A forked backend has no unit and so no `journalctl -u`, and snapserver's capture of its stderr is the only record on the host of why it failed.

## Enable vs. start, and the recorded source set

`enable` sets a unit to start at boot, and `start` runs it now. Infrastructure (`snapserver`, `snapclient`, `camilladsp`, `audera-streamer`) gets both unconditionally.

A catalogued source's units follow what the operator recorded. `~/.audera/sources.json` survives a flash, since this script writes only `/etc/*`, `/var/lib/*`, and unit files, so `activate_streamer_units` asks `audera streamer units --disabled` and `--enabled`, disables the first list `--now`, then enables and starts the second. The conf is rendered from the same record. It names no source and no unit, so a reprovision leaves the operator's sources running instead of reverting them, and the streams Snapserver serves and the units feeding them come from one answer. `--now` on the disable is what stops a backend a previous image left running; without it the flash's reboot would be the only thing that did.

With no file — a freshly flashed device — `get_enabled()` falls back to `audera.dal.sources.DEFAULT_ENABLED`, today `('AirPlay',)`. `nqptp` is enabled and started; `plexamp` and `plexamp-mdns` are installed but explicitly disabled, so the Sources tab can turn them on later. That is a fallback rather than a mirror: changing `DEFAULT_ENABLED`, or reordering `CATALOG` such that a different source leads, needs no change to the shell.

`test_the_provisioned_unit_state_mirrors_default_enabled` covers the unrecorded case and `test_provisioning_follows_a_recorded_enabled_set` the recorded one. Both directions of a break are silent on the device. A source in the enabled set left disabled ships a `snapserver.conf` naming a stream nothing feeds, and the Sources tab reports it enabled because it reads the enabled set rather than the unit. A source left running that the conf does not name ships a backend competing for a port for no reason.

Three orderings matter:

- The enabled sources' units get their own `systemctl start` line, before snapserver's, because snapserver forks shairport-sync and AirPlay's PTP clock must already own UDP 319/320. `systemctl start a b` enqueues its jobs concurrently rather than in written order. `snapserver.service`'s `After=nqptp.service` is a second safeguard on the same ordering, and `CATALOG` order puts `nqptp` first within the list.
- The apt install sits far above every `systemctl start`, so the binaries exist before anything forks them.
- Every `audera streamer conf …` render comes after `install_audera_cli`.

## Nothing seeds `~/.audera`, and nothing overwrites it

`setup.sh` writes `/etc/*`, `/var/lib/*`, and unit files only. `~/.audera/sources.json` is absent on a freshly flashed device by design: `dal.sources.get_enabled()` falls back to `DEFAULT_ENABLED`, so the data-access layer, the rendered `snapserver.conf`, and systemd agree without any Audera code having run to make them agree.

Seeding it would break `index.adopt_running_sources`, whose only way to tell an unrecorded device from one whose operator chose exactly `DEFAULT_ENABLED` is the file's absence. `test_provisioning_seeds_no_enabled_set` pins that.

It is also the reason provisioning reads the file rather than the constant. A reprovision of a device that has one leaves it untouched, and adoption cannot heal a divergence it opens: `adopt` refuses once a set is recorded. Provisioning that rendered `DEFAULT_ENABLED` over an operator's PlexAmp therefore stranded the device — every group reassigned to AirPlay at the first client connect, the Sources tab still reporting PlexAmp enabled, and `plexamp` disabled, which the claim probe reads as needing a claim again. The claim is why `sources.json` also carries `setup`: a completed claim is recorded there and outranks the live probe, so a reprovision that stops the unit does not re-ask for it.
