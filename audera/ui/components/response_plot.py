"""Frequency-response chart for the parametric-EQ editor"""

import math

from nicegui import ui

from audera.domains.dsp import response_curve
from audera.models.dsp import DSPConfig
from audera.ui.components import theme

# The visible frequency window (Hz); the y-axis auto-min tracks only the curve inside it.
_X_MIN = 20
_X_MAX = 20000
# The y-axis floors at -18 dB and extends downward in tidy 6 dB steps when a filter dips below.
_Y_MIN_FLOOR = -18
# The auto pre-amp keeps the curve ≤ 0 dB, so +5 is pure display headroom above unity.
_Y_MAX = 5


def _floor_to_6(value: float) -> int:
    """Rounds `value` down to the next lower multiple of 6 dB (keeps axis labels tidy)."""
    return math.floor(value / 6) * 6


def options(config: DSPConfig) -> dict:
    """Returns the ECharts option `dict` for a DSP configuration's response curve.

    Parameters
    ----------
    config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    frequencies, magnitudes = response_curve(config)
    # Auto-min tracks only the *visible* curve: `response_curve` grids from 1 Hz, but a pass
    # filter's steep sub-20 Hz rolloff would otherwise drag the axis to an off-screen extreme
    # (e.g. -60 dB) and squash the in-band curve. Window to [20, 20000] — always non-empty on the
    # 400-point log grid. The floor holds at -18 dB and drops in 6 dB steps only when a deep cut
    # inside the window demands it.
    visible = [m for f, m in zip(frequencies, magnitudes) if _X_MIN <= f <= _X_MAX]
    y_min = min(_Y_MIN_FLOOR, _floor_to_6(min(visible)))
    return {
        'grid': {'left': 28, 'right': 12, 'top': 10, 'bottom': 24},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {
            'type': 'log',
            'min': _X_MIN,
            'max': _X_MAX,
            # Only the endpoints carry a label — 20 Hz and 20 kHz — everything between is blank
            # (`:`-prefixed key → NiceGUI evaluates the value as a JS function; see echart.js).
            'axisLabel': {
                'showMinLabel': True,
                'showMaxLabel': True,
                ':formatter': "v => v <= 20 ? '20' : v >= 20000 ? '20k' : ''",
            },
            # Full vertical lines land on the log-axis decade ticks — within [20, 20000] that is
            # exactly 100 / 1000 / 10000.
            'splitLine': {'show': True, 'lineStyle': {'color': '#eeeeee'}},
            # Major ticks on the decades; minor ticks at the 2–9 subdivisions per decade
            # (30…90, 200…, 2k…). `minorSplitLine` off so only the three decades get a full line.
            'axisTick': {'show': True},
            'minorTick': {'show': True},
            'minorSplitLine': {'show': False},
            # Seat the axis line + 20/20k labels at the bottom of the grid rather than through
            # y=0 (the range is asymmetric, so y=0 sits well above the floor).
            'axisLine': {'onZero': False},
        },
        'yAxis': {
            'type': 'value',
            'min': y_min,
            'max': _Y_MAX,
            'interval': _Y_MAX - y_min,  # a single full-range step lands ticks only on the endpoints
            'axisLabel': {'formatter': '{value}'},
            'splitLine': {'lineStyle': {'color': '#eeeeee'}},
        },
        'series': [
            {
                'type': 'line',
                'data': [[f, m] for f, m in zip(frequencies, magnitudes)],
                'showSymbol': False,
                'smooth': True,
                'lineStyle': {'color': theme.INK, 'width': 2},
            }
        ],
    }


def render(config: DSPConfig) -> ui.echart:
    """Returns a full-width ECharts line element for a DSP configuration's response curve.

    Parameters
    ----------
    config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    return ui.echart(options(config)).classes('w-full h-40')
