"""Audio-source domain layer

The `sources` sub-package holds the audio-source catalog (`catalog`) and the two pure functions
that render `snapserver.conf`'s source lines from it.
"""

from audera.domains.sources.catalog import CATALOG, SourceDefinition, default_source, source_lines, source_units

__all__ = [
    'CATALOG',
    'SourceDefinition',
    'default_source',
    'source_lines',
    'source_units',
]
