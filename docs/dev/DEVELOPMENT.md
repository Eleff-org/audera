# Development

`audera` supports Python >= 3.11. Install from source using [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/Eleff-org/audera.git
cd audera
uv sync --all-extras
pre-commit install
```

## Commands

```bash
uv run ruff check --fix     # lint (max-line-length = 129)
uv run ruff format          # format
uv run ty check             # type check
uv run pytest tests/dal/ -v                          # DAL tests (no Docker required)
uv run pytest tests/clients/test_snapserver.py -v   # requires Docker
uv run pytest tests/clients/ -v                      # all client tests
uv run pytest -v                                     # everything
pre-commit run --all-files  # run all hooks manually
```

Install as a tool directly from GitHub:

```bash
uv tool install git+https://github.com/Eleff-org/audera.git
```

## Code style

- Type-hint all parameters and return values; use `Literal` for constrained string values
- Google-style docstrings
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants, `_leading_underscore` private
- Single quotes unless the string contains a single quote; f-strings for formatting
- 4-space indentation, 129-character line limit

## Package layout

List @audera/ for the Python package layout.

## Clients

- **SnapserverClient** (`clients/snapserver.py`): JSON-RPC 2.0 over WebSocket at `ws://host:1780/jsonrpc` (the HTTP server port). Opens a new connection per call. Methods: `get_status`, `get_clients`, `get_groups`, `get_stream_status`, `set_client_volume`, `set_client_latency`, `set_client_name`, `set_group_stream`, `set_group_mute`.
- **CamillaDSPClient** (`clients/camilladsp.py`): WebSocket at `ws://host:1234`. Methods: `get_config`, `set_config`, `get_volume`, `set_volume`.
- **PlexAmpClient** (`clients/plexamp.py`): HTTP at `http://host:32500` via `httpx`. Methods: `get_sessions`, `get_now_playing`, `play`, `pause`, `skip`.

## Data models

All seven models (`Band`, `DSPConfig`, `Preset`, `Player`, `Group`, `Settings`, `Stream`) are pydantic `BaseModel` with a `from_dict()` classmethod. Most also carry a hand-written `to_dict()` and a JSON `__repr__()`; `Player` and `Preset` do not, and serialize via `model_dump()` / `model_validate`.

- `Player` — Snapcast client: `id, host, port, connected, volume, muted, group_id`
- `Group` — Snapcast group: `id, name, client_ids, stream_id, muted, volume`
- `Stream` — the current PlexAmp playback state: `id, name, uri, status, current_track`. It is not a Snapcast stream and is not persisted.
- `DSPConfig` — parametric-EQ config: `player_id, preamp_db, bands, enabled`

`Player.group_id` and `Group.stream_id` are empty strings (not `None`) when unassigned.

## DAL

- `dsp`, `presets`, `settings`, and `sources` all persist via plain `json`. A `DSPConfig`'s and a `Preset`'s `bands` are nested lists of objects, which duckdb's `read_json_auto` cannot model, since it is flat/columnar under the pytensils DTYPES constraint. The duckdb-backed DALs were retired for the same reason.
- Config files: `~/.audera/{dsp,dsp/presets}/{id}.json` (`dsp` is keyed by `player_id`), `~/.audera/settings.json`, `~/.audera/sources.json`
