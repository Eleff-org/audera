"""Compute the true combined magnitude peak (dB) of a DSP configuration.

Drives the "protect headroom" guard: the suggested pre-amp attenuation is
`-response_peak_db`. Each enabled band's magnitude response is evaluated with
CamillaDSP's own `eval_filter` over a shared `logspace` grid (dependent only on
`samplerate`/`npoints`), summed element-wise, and offset by the flat pre-amp
Gain — matching the daemon's math so the guard can't drift from playback.
"""

from camilladsp_plot import eval_filter

from audera.domains.dsp.compiler import _band_to_biquad
from audera.models.dsp import DSPConfig

_SAMPLERATE = 48000


def response_peak_db(config: DSPConfig, samplerate: int = _SAMPLERATE) -> float:
    """Returns the combined magnitude peak in dB for a 0 dBFS input.

    Sums, element-wise over the shared frequency grid, the dB magnitude of every
    enabled band, then adds the scalar pre-amp Gain. The grid is identical across
    bands (it depends only on `samplerate`/`npoints`), so element-wise addition is
    valid. With no enabled bands the response is flat 0 dB, so the pre-amp value is
    returned directly.

    Parameters
    ----------
    config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    samplerate: `int`
        The sample rate in Hz for the magnitude evaluation (default 48000, matching
        the daemon/container config).
    """
    summed: list[float] = []
    for band in config.bands:
        if not band.enabled:
            continue
        magnitude = eval_filter(_band_to_biquad(band), samplerate=samplerate)['magnitude']
        if not summed:
            summed = list(magnitude)
        else:
            summed = [a + b for a, b in zip(summed, magnitude)]

    if not summed:
        return config.preamp_db
    return max(summed) + config.preamp_db
