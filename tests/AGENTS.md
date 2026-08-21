# tests/AGENTS.md

Conventions for the Audera test suite. List @tests/ for the layout.

## Philosophy

- Integration tests only: end-to-end behaviour as a user would exercise it, and only where the system is critical or complex. The CLI is tested as a process (`tests/cli/conftest.py`'s `audera_cli` runs the installed console script, so argparse's own refusals are under test).
- No class-based tests; pytest fixtures only. Prefer module-top imports (fixtures that gate on Docker import inline by necessity). Mirror the package structure under `tests/`. Parameterize over entrypoints/conditions where meaningful. Keep it DRY.

## DAL tests

Use the `audera_home` fixture from `conftest.py`: it monkeypatches the module-level `PATH` constant in each DAL module to point at `tmp_path`. Do not patch `audera.dal.path.HOME`, because the `PATH` constants are computed at import time and will not reflect a late patch. A child process sees neither, so anything that shells out passes the home in the child's environment (see the `env` handling in `tests/cli/conftest.py`).

## Client tests

| File | Strategy |
|---|---|
| `test_snapserver.py` | Real snapserver in a Debian Trixie testcontainer, pinned to `0.31.0-1` (Docker) |
| `test_snapserver_sources.py` | The same image booted with every catalogued source enabled |
| `test_camilladsp.py` | Real CamillaDSP binary in a custom testcontainer (Docker) |
| `test_plexamp.py` | `respx` HTTP mock over `httpx` |

## Systemd lane

`tests/systemd/` boots real systemd as PID 1 in a privileged container and `docker exec`s an inner pytest per module under `inside/`; the code under test runs *inside*. It is the only lane that observes a unit start, stop, or fail to stop, so it is authoritative where lanes disagree. Each `inside/test_*.py` docstring states what it pins. Run with `uv run pytest -m systemd -v` (opt-in, requires Docker); `-m systemd` *overrides* `addopts` rather than appending, which is why the driver passes the same flag to the inner pytest.

## Fixtures

Fixtures under `tests/fixtures/` are **captured from real running services** with the scripts in `tests/scripts/`; never hand-write fixture content. Each fixture directory has a `README.md` documenting what it holds and how to regenerate it. `tests/scripts/` also holds by-hand checks against a real streamer that pytest never collects; `check_airplay.py`'s docstring is the pattern.

## Running

```bash
uv run pytest tests/dal/ -v      # no Docker
uv run pytest tests/clients/ -v  # requires Docker
uv run pytest -v                 # everything except the systemd lane
uv run pytest -m systemd -v      # real systemd in a privileged container (Docker)
```
