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
        'grid': {'left': 44, 'right': 16, 'top': 16, 'bottom': 32},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {
            'type': 'log',
            'min': 20,
            'max': 20000,
            'axisLabel': {'formatter': '{value} Hz'},
            'splitLine': {'lineStyle': {'color': '#eeeeee'}},
        },
        'yAxis': {
            'type': 'value',
            'min': -18,
            'max': 18,
            'axisLabel': {'formatter': '{value} dB'},
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
    return ui.echart(options(config)).classes('w-full h-64')
