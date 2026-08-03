# ADR 002: Audio Quality Ceiling

**Date:** 2026-04-23
**Status:** Accepted

## Context

The Audera audio pipeline passes through several format conversion points between PlexAmp and the physical DAC. Each point constrains the maximum audio quality that can be delivered, regardless of the source material's original resolution.

The PlexAmp pipeline below is no longer the default path; a flashed device boots with AirPlay enabled (`dal.sources.DEFAULT_ENABLED`). The ceiling applies to every source; see *Per-source sample rates*.

## Pipeline summary

```
PlexAmp
  → ALSA default (pcm.plexamp_output)
  → snapcast_format plug (S16_LE conversion, 48000 Hz, stereo)
  → snapcast_raw (file: /tmp/snapfifo)
  → Snapserver (source: sampleformat=48000:16:2)
  → network
  → Snapclient (--sampleformat 48000:32:2 → hw:Loopback,0)
  → CamillaDSP (capture: S32LE from hw:Loopback,1)
  → CamillaDSP (playback: S32LE to hw:0 / hw:0,0)
  → DigiAMP+ DAC
```

## Decision

### Effective ceiling: 16-bit / 48 kHz

The ALSA `asound.conf` on the streamer converts all audio to `S16_LE` at 48000 Hz before writing to `/tmp/snapfifo`. The Snapserver `source` URI specifies `sampleformat=48000:16:2`. These two points cap the pipeline at CD quality (16-bit, 48 kHz stereo) regardless of what PlexAmp outputs.

#### Per-source sample rates

The pipeline above describes the PlexAmp source. The source catalog (`audera/domains/sources/catalog.py`) replaced the single hard-coded `source =` line, so the stream rate varies per source:

| Source | `sampleformat` | Set by |
|---|---|---|
| PlexAmp | `48000:16:2` | the catalog URI, matching `asound.conf`'s conversion |
| Spotify | `44100:16:2` | the catalog URI, matching go-librespot's fixed-rate pipe |
| AirPlay | `44100:16:2` | snapserver; the `airplay://` wrapper rewrites the query and ignores any supplied value, so the catalog URI must not state one |

Snapserver resamples each stream to the server default (`48000:16:2`) before encoding, and the playback chain stays 48 kHz throughout (ADR 003). The 44.1 kHz sources are upsampled, so the ceiling remains 16-bit / 48 kHz.

The downstream expansion from 16-bit to 32-bit (Snapclient `--sampleformat 48000:32:2`, CamillaDSP S32LE) is lossless zero-padding — it does not recover any information lost at the 16-bit conversion step and exists solely to satisfy CamillaDSP's minimum format requirements.

### Why this is acceptable now

- PlexAmp remote streaming typically delivers 16-bit FLAC or AAC, so the ceiling matches the common source format.
- The CamillaDSP pipeline currently has no filters or EQ active (`filters: {}`, `pipeline: []`); bit-depth headroom for DSP operations is moot.
- Changing the stream format requires coordinated changes across multiple files and has not been designed for runtime configurability.

### What must change to raise the ceiling

1. **`audera/cli/conf.py` (`render_asound`)** — Change the `snapcast_format` plug's `format` from `S16_LE` to `S32_LE` (or remove the conversion entirely and let Snapserver handle resampling).
2. **`audera/domains/sources/catalog.py`** — Change the PlexAmp entry's `uri` from `sampleformat=48000:16:2` to `48000:32:2` (or higher, e.g. `96000:32:2`). The rates of the other sources are fixed by their backends rather than by Audera.
3. **Both `setup.sh` files** — The Snapclient `--sampleformat` flag must match the new Snapserver format.
4. **`audera/cli/conf.py` (`render_camilladsp`)** — If the sample rate changes, `devices.samplerate` must be updated to match.

These four locations must always be kept in sync. There is currently no runtime validation that they agree.

## Consequences

- Source material above 16-bit or above 48 kHz is silently downsampled to 16-bit/48 kHz at the streamer.
- Adding DSP filters in CamillaDSP (EQ, room correction, crossover) operates on zero-padded 32-bit data; if high-resolution source support is added later, the DSP headroom is already present.
- A future configurable stream format feature must treat `asound.conf`, `snapserver.conf`, the Snapclient service unit, and the CamillaDSP config as a single atomic configuration unit.
