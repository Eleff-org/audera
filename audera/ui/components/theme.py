from nicegui import app

PRIMARY = '#1a1a2e'
SECONDARY = '#16213e'
ACCENT = '#0f3460'
TEXT = '#e0e0e0'
MUTED = '#888888'


def apply_defaults() -> None:
    app.colors(primary=PRIMARY, secondary=SECONDARY, accent=ACCENT)
