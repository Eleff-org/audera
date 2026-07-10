# AGENTS.md

## Commands

```bash
uv sync --all-extras        # install all dependencies including dev
uv run ruff check --fix     # lint (max-line-length = 129)
uv run ruff format          # format
uv run ty check             # type check
uv run python testing.py    # run ad-hoc tests (no formal test framework)
uv run pytest tests/dal/ -v                          # DAL tests (no Docker required)
uv run pytest tests/clients/test_snapserver.py -v   # requires Docker
uv run pytest tests/clients/ -v                      # all client tests
uv run pytest -v                                     # everything
pre-commit install          # install git hooks (run once after clone)
pre-commit run --all-files  # run all hooks manually
```

Install as a tool directly from GitHub:
```bash
uv tool install git+https://github.com/Eleff-org/audera.git
```

## Package layout

List @audera/ for the Python package layout.

## Architecture decisions

Significant technical and UX decisions are recorded in `docs/adrs/`. Consult the relevant ADR before changing behavior it covers, and add or update one when you make a decision of similar weight. List @docs/adrs/ for the catalog.

## Clients

- **SnapserverClient** (`clients/snapserver.py`): JSON-RPC 2.0 over WebSocket at `ws://host:1780/jsonrpc` (HTTP server port). Opens a new connection per call. Methods: `get_status`, `get_clients`, `get_groups`, `set_client_volume`, `set_group_stream`, `set_group_mute`.
- **CamillaDSPClient** (`clients/camilladsp.py`): WebSocket at `ws://host:1234`. Methods: `get_config`, `set_config`, `get_volume`, `set_volume`.
- **PlexAmpClient** (`clients/plexamp.py`): HTTP at `http://host:32500` via `httpx`. Methods: `get_sessions`, `get_now_playing`, `play`, `pause`, `skip`.

## Data models

All models are `@dataclass` with `from_dict()` / `from_config()` / `to_dict()` / `__repr__()` (JSON) / `__eq__()`.

- `Player` — Snapcast client: `id, host, port, connected, volume, muted, group_id`
- `DSPConfig` — parametric-EQ config: `player_id, preamp_db, bands, enabled` (keyed by `player_id`; the CamillaDSP pipeline is compiled from `preamp_db` + `bands` on Save)

The `dsp` models (`Band`/`DSPConfig`/`Preset`) are pydantic `BaseModel` (the `@dataclass` convention has drifted here); `Preset` (`id, name, bands`) serializes via `model_dump()`/`model_validate` — no hand-written `to_dict`.

## DAL

- `dsp`, `presets`, and `settings` all persist via plain `json` (not duckdb). A `DSPConfig`'s and a `Preset`'s `bands` are nested lists of objects, which duckdb's `read_json_auto` — flat/columnar under the pytensils DTYPES constraint — cannot model. The duckdb-backed DALs were retired, so every surviving DAL is plain-json for the same reason.
- Config files: `~/.audera/{dsp,dsp/presets,settings}/{id}.json` (`dsp` is keyed by `player_id`)

## Code style

- Type-hint all parameters and return values; use `Literal` for constrained string values
- Google-style docstrings
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants, `_leading_underscore` private
- Single quotes unless the string contains a single quote; f-strings for formatting
- 4-space indentation, 129-character line limit
