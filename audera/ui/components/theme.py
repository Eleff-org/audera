"""Brand theme adapter for NiceGUI / Quasar apps.

Serves ``brand/tokens.css`` and the self-hosted woff2 font files as NiceGUI
static assets, maps brand tokens to Quasar color slots, and injects page-level
CSS that applies the light palette.

Call ``apply_defaults()`` once from ``run()`` before ``ui.run()``.
Call ``apply_page()`` once per page render (after ``ui.header``).
"""

import importlib.resources
from pathlib import Path

from nicegui import app, ui

# ---- Brand token values (duplicated from tokens.css) ----
# Quasar's color slots are driven from the `--q-*` custom properties set in
# `_PAGE_CSS`, straight from the tokens, so no Python hex is needed there. These
# three remain because they feed consumers that cannot resolve a CSS `var()`: the
# header's inline `style=` and the ECharts canvas in `response_plot.py`. Keep them
# in sync with brand/tokens.css.
INK = '#1A1A18'
PAPER = '#FAFAF8'
PAPER_2 = '#F3F2EF'


def _brand_dir() -> Path:
    """Returns the brand directory.

    Checks the vendored package resource first (``audera/ui/static/brand/``),
    then falls back to ``brand/`` at the repo root for editable installs.
    """
    try:
        pkg_brand = Path(str(importlib.resources.files('audera.ui.static') / 'brand'))
        if pkg_brand.is_dir():
            return pkg_brand
    except ModuleNotFoundError:
        pass
    # Editable install or dev: brand/ lives at the repo root, one level above the audera package.
    return Path(str(importlib.resources.files('audera'))).parent / 'brand'


def _fonts_dir() -> Path:
    """Returns the fonts directory."""
    return _brand_dir() / 'fonts'


def apply_defaults() -> None:
    """Registers brand static files as NiceGUI assets.

    Must be called once from ``run()`` before ``ui.run()``. Quasar's color slots
    are set from the tokens in ``_PAGE_CSS`` (``--q-primary`` etc.), so no
    ``app.colors()`` call is needed.
    """
    app.add_static_files('/brand', str(_brand_dir()))
    app.add_static_files('/brand/fonts', str(_fonts_dir()))


# Page-level CSS that wires up the light brand palette. Injected once per page
# via ui.add_head_html so it lands after Quasar's defaults.
_PAGE_CSS = """
<link rel="stylesheet" href="/brand/tokens.css">
<style>
  /* Font faces (@font-face) are declared once in brand/tokens.css, linked
     above, so both apps and the website share one set. Do not restate them
     here. */

  /* Quasar color slots, driven straight from the brand tokens so tokens.css
     stays the single source of truth. Quasar reads these custom properties at
     runtime; this replaces an app.colors() call restating the same hex in
     Python. Linked after Quasar's defaults, so this :root block wins. */
  :root {
    --q-primary: var(--ink);
    --q-secondary: var(--ink-3);
    --q-accent: var(--ink);
    --q-positive: var(--up);
  }

  /* Light palette */
  body {
    background: var(--paper) !important;
    color: var(--ink) !important;
    font-family: var(--font-sans) !important;
  }
  .q-page {
    background: var(--paper) !important;
  }
  .q-tab-panel {
    background: var(--paper) !important;
  }

  /* Header wordmark: display serif, italic. Matches the website header. */
  .audera-wordmark {
    font-family: var(--font-display) !important;
    font-style: italic;
    font-weight: 400;
    font-size: var(--wordmark-size);
    font-variation-settings: 'opsz' 40, 'SOFT' 100, 'wght' 400;
    letter-spacing: -0.01em;
    line-height: 1;
  }

  /* Card headings: sans. A markdown **strong** word switches to the display
     serif italic, accenting a brand name or key term. */
  .audera-heading {
    font-family: var(--font-sans) !important;
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: 1.1;
  }
  .audera-heading strong {
    font-family: var(--font-display) !important;
    font-style: italic;
    /* Thin italic (wght 300) against the bold sans heading. Fraunces has a
       smaller x-height than Inter, so bump the size to align on one line. */
    font-size: 1.12em;
    font-weight: 300;
    font-variation-settings: 'opsz' 40, 'SOFT' 100, 'wght' 300;
    letter-spacing: -0.01em;
  }

  /* Markdown links: ink text, dotted underline that goes solid on hover.
     Scoped to markdown so buttons and chips are untouched. */
  .nicegui-markdown a {
    color: var(--ink);
    text-decoration: none;
    border-bottom: 1px dotted var(--ink-3);
    transition: border-bottom-color var(--duration) var(--ease);
  }
  .nicegui-markdown a:hover {
    border-bottom: 1px solid var(--ink);
  }

  /* Quasar button overrides: underline CTA style. Wrapped in @layer quasar so
     these win: Quasar's utility classes (.bg-primary, .text-white) live in that
     layer, and for !important declarations layer order is reversed, so an
     unlayered !important would lose to Quasar's. */
  @layer quasar {
    .q-btn {
      border-radius: var(--radius) !important;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: none !important;
      transition: all var(--duration) var(--ease);
    }
    .q-btn:not(.q-btn--flat) {
      background: none !important;
      color: var(--ink) !important;
      box-shadow: none !important;
      border: none !important;
      border-bottom: 1px solid var(--ink) !important;
      padding: 4px 0 !important;
      min-height: unset !important;
    }
    /* Quasar paints the elevation shadow on .q-btn::before, not .q-btn, so the
       box-shadow reset above never reaches it. Flatten the pseudo-element too. */
    .q-btn::before {
      box-shadow: none !important;
    }
    /* Flat icon buttons: ink when enabled, --ink-4 when disabled. Quasar's
       default disabled state (opacity 0.7 over --ink-3) leaves enabled and
       disabled nearly the same gray, so set an explicit color and reset opacity. */
    .q-btn--flat {
      color: var(--ink) !important;
    }
    .q-btn--flat:hover {
      color: var(--ink) !important;
    }
    .q-btn--flat.disabled {
      color: var(--ink-4) !important;
      opacity: 1 !important;
    }

    /* Segmented control (q-btn-toggle): single-select group. The reset above
       turns each segment into an underlined link with no selected state, so
       restyle as a bordered control with dividers and an ink-filled active
       segment (Quasar marks it .bg-primary/.text-white). */
    .q-btn-toggle {
      border: 1px solid var(--ink) !important;
      border-radius: 0 !important;
      box-shadow: none !important;
      overflow: hidden;
    }
    .q-btn-toggle .q-btn {
      background: none !important;
      color: var(--ink) !important;
      box-shadow: none !important;
      border: none !important;
      border-left: 1px solid var(--ink) !important;
      border-radius: 0 !important;
      padding: 6px 16px !important;
      min-height: unset !important;
    }
    .q-btn-toggle .q-btn:first-child {
      border-left: none !important;
    }
    .q-btn-toggle .q-btn.bg-primary,
    .q-btn-toggle .q-btn.text-white {
      background: var(--ink) !important;
      color: var(--paper) !important;
    }
  }
</style>
"""


def apply_page() -> None:
    """Injects brand CSS and font-face declarations into the current page.

    Call once per page render, after the header.
    """
    ui.add_head_html(_PAGE_CSS)
