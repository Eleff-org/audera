# tests/fixtures/plexamp

Fixtures captured from a real PlexAmp headless instance. **Never hand-write these files** — fabricated XML/JSON hides real API behaviour and causes tests to pass against data the service never actually returns.

## Regenerating

Requires PlexAmp headless running and reachable. Set `AUDERA_PLEXAMP_HOST` in `.env` (see `.env.example`), then:

```bash
# With a track actively playing:
uv run python tests/scripts/capture_plexamp_fixtures.py
```

The script writes:

| File | Captured when |
|---|---|
| `timeline_active.xml` | A track is playing (`state="playing"`) |
| `timeline_idle.xml` | Nothing is playing (`state="stopped"`) |
| `play.json` | Response body from `/player/playback/play` |
| `pause.json` | Response body from `/player/playback/pause` |
| `skip.json` | Response body from `/player/playback/skipNext` |

Capture `timeline_active.xml` and `timeline_idle.xml` separately — run the script while a track is playing for the active fixture, then again after stopping playback for the idle fixture. Commit both files alongside any changes to `test_plexamp.py`.
