# tests/AGENTS.md

This file describes conventions for the Audera test suite. The reasoning behind any particular
fixture or probe lives beside it, in the code it explains.

## Philosophy

- Integration tests only — test end-to-end behaviour as a user would
- Only where the system is critical or of reasonable complexity
- The CLI is tested as a process, not as an import — `tests/cli/conftest.py`'s `audera_cli` runs the installed console script, so argparse's own refusals are under test rather than a call shape the CLI cannot make
- No class-based tests — pytest fixtures only
- No inline imports — all imports at module top level
- Mirror package structure under `tests/`
- Parameterize over different entrypoints/conditions where meaningful
- DRY — no duplicate fixtures or tests

## Structure

List @tests/ for the test package layout.

## DAL tests

DAL tests use the `audera_home` fixture from `conftest.py`. It monkeypatches the module-level `PATH`
constant in each DAL module to point at a `tmp_path` subdirectory, so no real `~/.audera` files are
touched.

Do not patch `audera.dal.path.HOME` — the `PATH` constants are computed at import time and will not
reflect a late patch.

A child process sees neither, so anything that shells out passes the home in the child's environment:
`tests/cli/conftest.py` and `inside/conftest.py`'s `provision()` both do. Set `HOME` **and**
`USERPROFILE`, and clear `HOMEDRIVE`/`HOMEPATH`. `ntpath.expanduser` never reads `HOME`, so a
POSIX-shaped `env=` leaks the developer's own `~/.audera` into the test on Windows — silently, and
with output plausible enough to read as a pass.

## Client tests

| File | Strategy |
|---|---|
| `test_snapserver.py` | Real snapserver in a Debian Trixie testcontainer, pinned to `0.31.0-1` to match the device (requires Docker) |
| `test_snapserver_sources.py` | The same image booted from a conf with every catalogued source enabled (`snapserver_container_all_sources`). The image carries stub `go-librespot` and `shairport-sync` binaries that write silence, so `process://` and `airplay://` streams start. It covers conf acceptance and stream registration, not backend behaviour |
| `test_camilladsp.py` | Real CamillaDSP binary in a custom testcontainer (requires Docker) |
| `test_plexamp.py` | `respx` HTTP mock intercepting `httpx` calls |

## Systemd lane

`tests/systemd/` boots real systemd as PID 1 in a privileged Debian container and `docker exec`s an
inner pytest per module under `inside/`. The code under test runs *inside*; the host half is only the
driver. It is the only lane that observes a unit start, stop, or fail to stop, so where it disagrees
with anything else it is authoritative.

| Module | Pins |
| :--- | :--- |
| `test_platform.py` | `@platform.requires('dietpi')` on its *passing* branch, and that the image ships no Audera unit file |
| `test_system.py` | The seam's effects — `start`/`stop` moving `ActiveState`, `MainPID` and reaping; `is_active` against genuinely failed and unknown units; `daemon-reload` moving a unit out of `not-found` |
| `test_index.py` | The toggle choreography as an effect: the running streams match the conf on disk, a listener is moved to the destination the operator chose, a disabled source leaves no process, no zombie and no orphan, every unit stops inside the seam's budget, and a toggle applies against a unit systemd's start rate limit has already refused |
| `test_plex.py` | The claim drop-in — the token reaching `/proc/<pid>/environ`, the chip ladder, and `_active_seconds` sharing an epoch with `time.monotonic()` |
| `test_provisioning.py` | What a flash installs, including the unit state a recorded `sources.json` implies, and the `dal.sources.DEFAULT_ENABLED` fallback when there is none |

**What it does not confirm.** The stubs are stubs, so nothing here covers backend behaviour, audio,
ALSA, sync, DSP correctness, the apt pins, the DietPi repo, NetworkManager, the reboot tail, or ARM
timing; `os/dietpi/AGENTS.md` lists what is still verified by flashing a device. A green lane means
the choreography is right and nothing leaks. It does not mean the streamer works.

## Fixtures

Fixtures under `tests/fixtures/` are **captured from real running services** using the scripts in
`tests/scripts/`. Never hand-write or invent fixture content — fabricated responses hide real API
behaviour and cause tests to pass against data that the service never actually returns.

Each fixture directory contains a `README.md` that documents what the fixtures contain and how to
regenerate them.

`tests/scripts/` also holds checks that are run by hand against a real streamer over the network and
are never collected by pytest; `check_airplay.py`'s docstring is the pattern for adding another.

## Running

```bash
uv run pytest tests/dal/ -v                          # DAL only — no Docker required
uv run pytest tests/clients/test_snapserver.py -v   # requires Docker
uv run pytest tests/clients/ -v                      # all client tests
uv run pytest -v                                     # everything except the systemd lane
uv run pytest -m systemd -v                          # real systemd in a privileged container (requires Docker)
```

`-m systemd` on the command line *overrides* `addopts` rather than appending to it, which makes the
lane opt-in and is why the driver passes the same flag to the inner pytest.
