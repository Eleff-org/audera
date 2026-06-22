# tests/AGENTS.md

This file describes conventions for the Audera test suite.

## Philosophy

- Integration tests only — test end-to-end behaviour as a user would
- Only where the system is critical or of reasonable complexity
- No class-based tests — pytest fixtures only
- No inline imports — all imports at module top level
- Mirror package structure under `tests/`
- Parameterize over different entrypoints/conditions where meaningful
- DRY — no duplicate fixtures or tests

## Structure

List @tests/ for the test package layout.

## DAL tests

DAL tests use the `audera_home` fixture from `conftest.py`.  It monkeypatches
the module-level `PATH` constant in each DAL module to point at a `tmp_path`
subdirectory, so no real `~/.audera` files are touched.

Do not patch `audera.dal.path.HOME` — the `PATH` constants are computed at
import time and will not reflect a late patch.

## Client tests

| File | Strategy |
|---|---|
| `test_snapserver.py` | Real snapserver in a Debian Bookworm testcontainer (requires Docker) |
| `test_camilladsp.py` | Real CamillaDSP (Dummy backend) in a custom testcontainer (requires Docker) |
| `test_plexamp.py` | `respx` HTTP mock intercepting `httpx` calls |

The CamillaDSP test image must be built locally before running:

```bash
docker build -t camilladsp-test:latest tests/docker/camilladsp/
```

## Fixtures

Fixtures under `tests/fixtures/` are **captured from real running services** using the scripts in `tests/scripts/`. Never hand-write or invent fixture content — fabricated responses hide real API behaviour and cause tests to pass against data that the service never actually returns.

Each fixture directory contains a `README.md` that documents what the fixtures contain and how to regenerate them.

## Running

```bash
uv run pytest tests/dal/ -v                          # DAL only — no Docker required
uv run pytest tests/clients/test_snapserver.py -v   # requires Docker
uv run pytest tests/clients/ -v                      # all client tests
uv run pytest -v                                     # everything
```
