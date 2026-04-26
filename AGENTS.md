# AGENTS.md

This file provides guidance to coding agents when working with code in this repository. For project status, migration history, planned workstreams, and release milestones, see `PROJECT.md`.

## Commands

```bash
uv sync --all-extras        # install all dependencies including dev
uv run ruff check --fix     # lint (max-line-length = 129)
uv run ruff format          # format
uv run ty check             # type check
uv run python testing.py    # run ad-hoc tests (no formal test framework)
uv run pytest tests/dal/ -v                          # DAL tests (no Docker required)
uv run pytest tests/services/test_snapserver.py -v  # requires Docker
uv run pytest tests/services/ -v                     # all service tests
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

## Services

- **SnapserverClient** (`services/snapserver.py`): JSON-RPC 2.0 over WebSocket at `ws://host:1780/jsonrpc` (HTTP server port). Opens a new connection per call. Methods: `get_status`, `get_clients`, `get_groups`, `set_client_volume`, `set_group_stream`, `set_group_mute`.
- **CamillaDSPClient** (`services/camilladsp.py`): WebSocket at `ws://host:1234`. Methods: `get_config`, `set_config`, `get_volume`, `set_volume`.
- **PlexAmpClient** (`services/plexamp.py`): HTTP at `http://host:32500` via `httpx`. Methods: `get_sessions`, `get_now_playing`, `play`, `pause`, `skip`.

## Data models

All models are `@dataclass` with `from_dict()` / `from_config()` / `to_dict()` / `__repr__()` (JSON) / `__eq__()`.

- `Player` — Snapcast client: `id, host, port, connected, volume, muted, group_id`
- `Group` — Snapcast group: `id, name, client_ids, stream_id, muted, volume`
- `Stream` — Plex-Amp stream: `id, name, uri, status, current_track`
- `DSPConfig` — CamillaDSP pipeline: `id, player_id, pipeline (dict), enabled`

`Player.group_id` and `Group.stream_id` are empty strings (not `None`) when unassigned — required by the pytensils `'str'` DTYPES constraint.

## DAL

- `players`, `groups`, `streams` use `pytensils.config.Handler` + DuckDB for bulk queries via `read_json_auto`.
- `dsp` uses plain `json` — the pipeline dict is too complex for DTYPES validation.
- Config files: `~/.audera/{players,groups,streams,dsp}/{id}.json`

## Code style

- Type-hint all parameters and return values; use `Literal` for constrained string values
- Google-style docstrings
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants, `_leading_underscore` private
- Single quotes unless the string contains a single quote; f-strings for formatting
- 4-space indentation, 129-character line limit
