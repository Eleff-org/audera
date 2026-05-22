from nicegui import ui


def render(title: str, subtitle: str) -> None:
    with ui.header().classes('bg-primary text-white items-center'):
        ui.label(title).classes('text-xl font-bold')
        ui.label(subtitle).classes('text-sm ml-2 opacity-75')
