"""Reusable page-layout primitives"""

from nicegui import ui


def fill_viewport() -> None:
    """Makes the current page fill the viewport so a `grow` child can own the only scroll region.

    NiceGUI wraps each page in `q-layout → q-page-container → q-page → .nicegui-content`. Quasar
    already sizes `q-page` to the viewport minus the fixed header (a JS-managed `min-height` that
    tracks `window.innerHeight`, so it is `dvh`-equivalent and updates on resize/rotation), but
    neither wrapper propagates that as a definite height, so a page's `grow` child only grows within
    its content. Making both wrappers filling flex columns hands the whole header-offset + viewport
    math to Quasar: a page that calls this and gives its root column `grow min-h-0` fills the leftover
    height with no per-page pixel/rem constant.

    `ui.query()` targets only the current page's DOM (each client renders its own tree), so this is
    opt-in per page and never affects other routes.
    """
    ui.query('.q-page').classes('flex flex-col')  # cooperate with Quasar's managed min-height
    # `grow`/`min-h-0` fill the leftover height (flex `min-height: auto` would otherwise pin it to content).
    # `w-full`/`min-w-0` are the width twins: as a flex item this box otherwise sizes to its *content* — a
    # wide element (e.g. the DSP chart canvas) would push it (and the page) past the viewport, forcing a
    # mobile zoom-out. `w-full` re-imposes the definite `width: 100%` it had as a block, clamped to `q-page`.
    ui.query('.nicegui-content').classes('grow min-h-0 w-full min-w-0')
