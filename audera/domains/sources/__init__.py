"""Audio-source domain layer

Holds the audio-source catalog (`catalog`) and the pure functions that derive `snapserver.conf`'s
source lines, default source, and systemd units from it.
"""

from audera.domains.sources.catalog import CATALOG, SourceDefinition, default_source, source_lines, source_units

__all__ = [
    'CATALOG',
    'SourceDefinition',
    'default_source',
    'source_lines',
    'source_units',
]
