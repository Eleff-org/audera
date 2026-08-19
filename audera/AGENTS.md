# AGENTS.md

Backend conventions for the `audera` Python package. Commands, the architecture-decision workflow, and code style live in the root `AGENTS.md`; UI conventions in `audera/ui/AGENTS.md`.

## Clients

Each client (`clients/snapserver.py`, `camilladsp.py`, `plexamp.py`) is a synchronous class constructed with `(host, port)`. Snapserver and CamillaDSP funnel every request through a private `_call` that opens a fresh connection per call and translates transport failures to `Unreachable` and service rejections to `ServiceError`. PlexAmp is the exception: plain `httpx`, no typed translation. Protocol, port, and method list live in each class docstring.

## Services

Host-level side effects live in `audera/services/`, never inline in the UI or CLI. Functions that touch the device are gated with `@platform.requires('dietpi')`, which raises `RuntimeError` at call time (not a `CommandError`). All `systemctl` goes through `services/system.py`; the one exception is `services/ap.py`, which still shells out inline.

## Configuration writes

Every configuration write (the DALs, `/etc/snapserver.conf`, the PlexAmp claim drop-in, the access point's dnsmasq conf) goes through `audera/io.py`'s `write_text`, which writes a sibling temp and `os.replace`s it so a reader sees the whole old or whole new file. Pass `mode=` for files carrying secrets (the claim drop-in is `0o600`).

## Audio sources

`audera/domains/sources/catalog.py`'s `CATALOG` is the single vocabulary for audio sources; its docstring owns the invariants (immutable ids, at least one enabled, a live `default_source`). Two words, following `snapserver.conf`'s own split:

- **source** — a `SourceDefinition` an operator enables and provisions. Owns the Sources tab, `sources.json`, `default_source`, the `source =` lines, and systemd units.
- **stream** — the Snapcast runtime object a group listens to. Owns `stream_id`, `Group.SetStream`, and the Players tab's assignment surface.

Audera owns which sources run (the enabled set, and therefore `snapserver.conf`); Snapcast owns which player listens to what (it persists group membership and `stream_id` in its own `server.json`, so Audera stores no assignment and reads it live).

## Errors

`audera/errors.py` defines `CommandError` and its subclasses `Unreachable`, `ServiceError`, and `StorageError`. Each client and service boundary translates raw exceptions into the typed equivalent; UI write handlers catch `CommandError`. See ADR 006 for the translation table.
