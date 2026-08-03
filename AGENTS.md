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
uv run pytest -v                                     # everything except the systemd lane
uv run pytest -m systemd -v                          # real systemd in a privileged container (requires Docker)
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

- **SnapserverClient** (`clients/snapserver.py`): JSON-RPC 2.0 over WebSocket at `ws://host:1780/jsonrpc` (HTTP server port). Opens a new connection per call. Methods: `get_status`, `get_clients`, `get_groups`, `get_stream_status`, `set_client_volume`, `set_client_latency`, `set_client_name`, `set_group_stream`, `set_group_mute`.
- **CamillaDSPClient** (`clients/camilladsp.py`): WebSocket at `ws://host:1234`. Methods: `get_config`, `set_config`, `get_volume`, `set_volume`.
- **PlexAmpClient** (`clients/plexamp.py`): HTTP at `http://host:32500` via `httpx`. Methods: `get_sessions`, `get_now_playing`, `play`, `pause`, `skip`.

## Services

Host-level side effects live in `audera/services/`, never inline in the UI or the CLI. Functions that touch the device are gated with `@platform.requires('dietpi')`, which raises `RuntimeError` at *call* time so they do not mutate a developer's own machine.

- **system** (`services/system.py`): the systemd seam. `systemctl(*args, check=True)` returns the `CompletedProcess`. `is_active(unit)` returns a `bool` and does not `check`, since `systemctl is-active` exits 3 for a stopped unit. Nothing else calls `subprocess.run(['systemctl', …])` directly, so the ordering of an enable or a disable stays assertable against one seam. `TIMEOUT` bounds every call. Every call captures output and logs a failure's `stderr` before re-raising the `CalledProcessError`, whose `__str__` carries the argv and exit status but not the reason; a caller that renders the exception must read `exc.stderr`.
- **platform** (`services/platform.py`): `NAME` / `VERSION`, read from `/boot/dietpi/.version`, and the `requires()` decorator.
- **netifaces** (`services/netifaces.py`): `nmcli` — Wi-Fi scan, connect, and connection state.
- **ap** (`services/ap.py`): the setup-mode Wi-Fi access point. Still shells out to `systemctl` inline; moving it onto `system` is a follow-up.
- **logging** (`services/logging.py`): the shared logger.

## Data models

All seven models (`Band`, `DSPConfig`, `Preset`, `Player`, `Group`, `Settings`, `Stream`) are pydantic `BaseModel` with a `from_dict()` classmethod. There is no `from_config()`. Most carry a hand-written `to_dict()` and a JSON `__repr__()`; `Player` and `Preset` do not, and serialize via `model_dump()` / `model_validate`.

- `Player` — Snapcast client: `id, host, port, connected, volume, muted, group_id`
- `DSPConfig` — parametric-EQ config: `player_id, preamp_db, bands, enabled` (keyed by `player_id`; the CamillaDSP pipeline is compiled from `preamp_db` + `bands` on Save)

## DAL

- `dsp`, `presets`, `settings`, and `sources` all persist via plain `json` (not duckdb). A `DSPConfig`'s and a `Preset`'s `bands` are nested lists of objects, which duckdb's `read_json_auto` — flat/columnar under the pytensils DTYPES constraint — cannot model. The duckdb-backed DALs were retired, so every surviving DAL is plain-json for the same reason.
- Config files: `~/.audera/{dsp,dsp/presets}/{id}.json` (`dsp` is keyed by `player_id`), `~/.audera/settings.json`, `~/.audera/sources.json`
- Every configuration write goes through `audera/io.py`'s `write_text(path, content, *, encoding='utf-8', mode=None)` — the DALs, `/etc/snapserver.conf`, the PlexAmp claim drop-in (`mode=0o600`, it carries a plex.tv token), and the access point's dnsmasq conf. It takes already-rendered content, writes a sibling temp, and `os.replace`s it into place, so a concurrent reader sees either the old file or the new one and a failure leaves the old one. `mode` is applied to the temp, since `os.replace` carries the source's bits. `os/dietpi/streamer/automation/setup.sh` renders to `.tmp` and `mv`s for the same reason.

## Audio sources

`audera/domains/sources/catalog.py`'s `CATALOG` is the single vocabulary for audio sources: provisioning, the Sources tab, the Players tab, and `render_snapserver()` all derive from it. A source's id, URI, and units are not restated anywhere else.

`~/.audera/sources.json` holds `{'sources': {'enabled': [...], 'setup': {id: {...}}}}` via `dal.sources`. `enabled` is which sources the operator wants running; a source absent from the list is disabled. `setup` is the durable record of a source's one-time setup, today only `{'complete': true}` for a claimed PlexAmp, read by `index._setup_state` ahead of any live probe and discarded when the source is disabled. The probes report what the device does *now* — a stopped unit reads as unclaimed — so without the record a reprovision re-asks for a claim that already happened. Every writer reads the whole document and re-writes it, so the two sections cannot clobber each other, and `is_recorded()` tests the `enabled` key rather than the file, since a setup write creates the file too.

Applying a toggle to the host is `audera/domains/sources/toggle.py`'s `apply(source, enable, enabled_ids)`. In order, it writes `snapserver.conf`, clears the start-limit counter of every unit it is about to start, moves the source's units through the `system` seam, and restarts Snapserver. Clearing the counters is required: each toggle restarts Snapserver, systemd's default start limit counts manual starts, and without the clear the sixth toggle inside ten seconds is refused, leaving the server dead and `Restart=on-failure` unable to recover it. `apply` takes the enabled ids instead of reading them back, so the conf cannot be rendered from a set other than the one the caller recorded. It takes no `page`; the lock, the data-access-layer write, group reassignment, the readiness wait, and the notifications stay in `ui/streamer/pages/index.py`.

**The ownership split:** Audera owns which sources run (the enabled set, and therefore the rendered `snapserver.conf`). Snapcast owns which player listens to what. It persists group membership and `stream_id` in its own `server.json`, so Audera stores no assignment and reads it live.

Audera uses two words for this, following `snapserver.conf`'s own split between `source = <uri>` per input and `default_source`:

- **source** — a `SourceDefinition` an operator enables and provisions. Owns the Sources tab, `sources.json`, `default_source`, the `source =` lines, setup flows, and systemd units.
- **stream** — the Snapcast runtime object a group listens to. Owns `stream_id`, `Group.SetStream`, `get_stream_status`, the `[stream]` conf section, and the Players tab's assignment surface.

The Players tab's "Stream" caption, its "By stream" grouping, and `FF_GROUPING_BY_STREAM = 'stream'` are correct as written.

Three rules follow from upstream Snapcast behaviour. Record an ADR before contradicting one:

1. A `SourceDefinition.id` is immutable. It is also the Snapcast stream name, so renaming it orphans every group Snapcast persisted against it. Change `label` instead.
2. At least one source must stay enabled. Snapserver dereferences a null default stream at the first client connect, so a zero-stream conf crashes it; `render_snapserver()` raises instead of emitting one.
3. `default_source` must always be set and must name a live stream. Removing a stream reassigns its groups to `default_source`, and naming a stream that is not live mis-routes them with no error. `default_source()` derives the value, so no caller can supply one.

The bootstrap set is `dal.sources.DEFAULT_ENABLED`, today `('AirPlay',)`, the only source that plays with no account, claim, or pairing. It is a fallback for a device with no recorded set, never a value that overwrites one: `get_enabled()` degrades to it, and provisioning renders both the conf (`audera streamer conf snapserver.conf`) and the systemd unit state (`audera streamer units --enabled` / `--disabled`) from `get_enabled()`. On a flashed device, which has no `sources.json`, that is AirPlay's units enabled and started and every other source's installed but disabled; on a reprovision it is whatever the operator recorded, since `sources.json` survives a flash. The shell names no source, so changing `DEFAULT_ENABLED` or reordering `CATALOG` is a change to Python alone; see `os/dietpi/AGENTS.md`.

`index.adopt_running_sources`, called once from `Page.__init__`, seeds an absent `sources.json` from the streams Snapserver is serving ∩ `CATALOG`. The enabled set is the sole input to the conf rewrite, so on an in-place upgrade this keeps the first toggle from truncating a pre-existing stream out of `/etc/snapserver.conf` without the disable path's reassignment safeguard firing. Adoption writes nothing on an unreachable Snapserver or an empty intersection, so the next load retries.

## Code style

- Type-hint all parameters and return values; use `Literal` for constrained string values
- Google-style docstrings
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants, `_leading_underscore` private
- Single quotes unless the string contains a single quote; f-strings for formatting
- 4-space indentation, 129-character line limit
