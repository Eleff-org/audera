from nicegui import ui

from audera.ui.components import theme


def render(title: str, subtitle: str | None = None) -> None:
    with ui.header().classes('items-center').style(f'background: {theme.INK}; color: {theme.PAPER};'):
        ui.label(title).classes('audera-wordmark')
        if subtitle:
            ui.label(subtitle).classes('text-sm ml-2 opacity-75')
    theme.apply_page()
