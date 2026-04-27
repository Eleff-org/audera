"""Data-access layer"""

import os

from audera.dal import dsp, groups, identities, players, settings, streams

__all__ = ['identities', 'players', 'groups', 'streams', 'dsp', 'settings']

PATH = os.path.abspath(os.path.join(os.path.expanduser('~'), '.audera'))
