"""Frequency-response chart for the parametric-EQ editor"""

from nicegui import ui

from audera.domains.dsp import response_curve
from audera.models.dsp import DSPConfig
from audera.ui.components import theme


def options(config: DSPConfig) -> dict:
    """Returns the ECharts option `dict` for a DSP configuration's response curve.

    Parameters
    ----------
    config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    frequencies, magnitudes = response_curve(config)
    return {
        'grid': {'left': 28, 'right': 12, 'top': 10, 'bottom': 20},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {
            'type': 'log',
            'min': 20,
            'max': 20000,
            # Only the endpoints carry a label — 20 Hz and 20 kHz — everything between is blank
            # (`:`-prefixed key → NiceGUI evaluates the value as a JS function; see echart.js).
            'axisLabel': {
                'showMinLabel': True,
                'showMaxLabel': True,
                ':formatter': "v => v <= 20 ? '20' : v >= 20000 ? '20k' : ''",
            },
            'splitLine': {'show': False},
        },
        'yAxis': {
            'type': 'value',
            'min': -18,
            'max': 18,
            'interval': 36,  # a single 36 dB step lands ticks only on the ±18 endpoints
            'axisLabel': {'formatter': '{value}'},
            'splitLine': {'lineStyle': {'color': '#eeeeee'}},
        },
        'series': [
            {
                'type': 'line',
                'data': [[f, m] for f, m in zip(frequencies, magnitudes)],
                'showSymbol': False,
                'smooth': True,
                'lineStyle': {'color': theme.ACCENT, 'width': 2},
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
