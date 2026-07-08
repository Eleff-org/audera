"""Compute the combined magnitude response and clip-safe pre-amp of a DSP configuration.

Bands are the source of truth; this module derives everything downstream from the same
element-wise sum. Each enabled band's magnitude response is evaluated with CamillaDSP's
own `eval_filter` over a shared `logspace` grid (dependent only on `samplerate`/`npoints`),
summed, and offset by the flat pre-amp Gain — matching the daemon's math so the live chart,
the automatic pre-amp ceiling, the headroom peak, and the compiled pipeline can never drift
apart. `logspace` is not re-exported from the package root, so it is imported from the
submodule that also backs `eval_filter`.
"""

from camilladsp_plot import eval_filter
from camilladsp_plot.eval_filterconfig import logspace

from audera.domains.dsp.compiler import _band_to_biquad
from audera.models.dsp import Band, DSPConfig

_SAMPLERATE = 48000
_CHART_NPOINTS = 400
_SAFETY_NPOINTS = 1000


def _summed_magnitude(bands: list[Band], samplerate: int, npoints: int) -> list[float]:
    """Returns the element-wise dB-magnitude sum of every enabled band over the grid.

    The grid is identical across bands (it depends only on `samplerate`/`npoints`), so
    element-wise addition is valid. A full-length list of zeros is returned when no band
    is enabled, so the response axis exists with no band firing.

    Parameters
    ----------
    bands: `list[audera.models.dsp.Band]`
        The parametric-EQ bands to sum.
    samplerate: `int`
        The sample rate in Hz for the magnitude evaluation.
    npoints: `int`
        The number of points on the shared frequency grid.
    """
    summed = [0.0] * npoints
    for band in bands:
        if not band.enabled:
            continue
        magnitude = eval_filter(_band_to_biquad(band), samplerate=samplerate, npoints=npoints)['magnitude']
        summed = [a + b for a, b in zip(summed, magnitude)]
    return summed


def response_curve(
    config: DSPConfig,
    samplerate: int = _SAMPLERATE,
    npoints: int = _CHART_NPOINTS,
) -> tuple[list[float], list[float]]:
    """Returns the combined frequency-response curve `(frequencies, magnitudes)` in dB.

    `frequencies` is bit-identical to `eval_filter`'s `'f'` vector (same `logspace` call),
    so the grid holds even with no band enabled. The scalar pre-amp Gain is added onto the
    summed band magnitude, matching the daemon's flat pre-amp filter.

    Parameters
    ----------
    config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    samplerate: `int`
        The sample rate in Hz for the magnitude evaluation (default 48000, matching the
        daemon/container config).
    npoints: `int`
        The number of points on the frequency grid (default 400 — cheap and smooth for the
        chart).
    """
    frequencies = logspace(1.0, samplerate * 0.95 / 2.0, npoints)
    summed = _summed_magnitude(config.bands, samplerate, npoints)
    return frequencies, [config.preamp_db + m for m in summed]


def response_peak_db(config: DSPConfig, samplerate: int = _SAMPLERATE) -> float:
    """Returns the combined magnitude peak in dB for a 0 dBFS input.

    Delegates to `response_curve` at the historical fine grid (`npoints=1000`), so the
    numeric result is identical to the pre-split implementation. With no enabled bands the
    response is flat, so the peak equals the pre-amp value.

    Parameters
    ----------
    config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    samplerate: `int`
        The sample rate in Hz for the magnitude evaluation (default 48000, matching the
        daemon/container config).
    """
    return max(response_curve(config, samplerate, npoints=_SAFETY_NPOINTS)[1])


def auto_preamp_db(bands: list[Band], samplerate: int = _SAMPLERATE, margin_db: float = 0.0) -> float:
    """Returns the clip-safe pre-amp ceiling in dB for a set of bands.

    The ceiling is `-(max(0, bands_peak) + margin_db)`: it attenuates by the combined boost
    so the response never exceeds 0 dBFS, and is `0.0` for all-cut or no-enabled bands (a
    net-cut response needs no attenuation). Evaluated on the fine 1000-point grid — a coarse
    grid could under-sample a high-Q peak and over-optimize the ceiling.

    Takes `bands` rather than a `DSPConfig` because it never reads the pre-amp: it derives a
    ceiling from the band shapes alone (a future preset that stores no pre-amp can do the
    same).

    Parameters
    ----------
    bands: `list[audera.models.dsp.Band]`
        The parametric-EQ bands to derive the ceiling from.
    samplerate: `int`
        The sample rate in Hz for the magnitude evaluation (default 48000, matching the
        daemon/container config).
    margin_db: `float`
        Extra headroom in dB reserved below 0 dBFS (default 0.0).
    """
    summed = _summed_magnitude(bands, samplerate, npoints=_SAFETY_NPOINTS)
    return -(max(0.0, max(summed)) + margin_db)
