# Brand

`brand/` defines palette, typography, shape, and motion for both the Audera website and the NiceGUI apps. `tokens.css` is the single source of truth: every value is a CSS custom property on `:root` with an inline comment on its role. Consumers use `var(--token)`; nothing hard-codes a hex value.

## Principles

1. **Monochrome.** Ink and paper only. The one non-monochrome token is `--accent-wash`, the `::selection` highlight; there is no general-purpose accent.
2. **Precision over ornament.** Structure comes from alignment, spacing, and restraint, not decoration.
3. **Zero border radius** (`--radius: 0`). Every element is square.
4. **Underline CTAs and ghost chips.** No filled or colored buttons.
5. **Motion only where it communicates state**, via `--duration` / `--ease`.
6. **Light theme only.** One token set, no dark-mode toggle.

## Typography

Three self-hosted variable fonts, vendored under `fonts/` as woff2 (no CDN, so the setup app serves offline), all SIL OFL from Google Fonts, Latin subset. The `@font-face` rules are declared once in `tokens.css`; no other file restates them.

- **Fraunces** (display) — wordmark, headings, pull quotes; italic weight 300 for brand emphasis.
- **Inter** (sans) — UI text and body copy.
- **JetBrains Mono** (mono) — data, metadata, technical values.

Per-role `font-variation-settings` live where they are used (`website/index.html` and `audera/ui/components/theme.py`).

## Quasar / NiceGUI color slots

| Quasar slot | Brand token |
|---|---|
| `primary` | `--ink` |
| `secondary` | `--ink-3` |
| `accent` | `--ink` |
| `positive` | `--up` |

`audera/ui/components/theme.py`'s `_PAGE_CSS` sets Quasar's runtime custom properties (`--q-primary`/`-secondary`/`-accent`/`-positive`) straight from the tokens (`--q-primary: var(--ink)`, …), so `tokens.css` drives the slots with no Python hex to hand-sync and no `app.colors()` call. The paper background is applied as CSS (`background: var(--paper)` in `theme.py`), not a Quasar color slot. `theme.py` still keeps three hex constants (`INK`, `PAPER`, `PAPER_2`) for the two consumers that cannot resolve a CSS `var()`: the header's inline `style=` and the ECharts canvas in `response_plot.py`.

## Consuming tokens

- **Apps (NiceGUI):** `theme.py` serves `tokens.css` and fonts via `app.add_static_files()` and maps tokens to Quasar's `--q-*` slots in CSS. See `audera/ui/AGENTS.md`.
- **Website (static):** `website/build.py` copies `tokens.css` and `fonts/` into `website/_site/brand/`, and the hand-written `website/index.html` links `brand/tokens.css` directly. The hero image uses `--radius-media` (12px) for rounded corners; the app default stays square (`--radius: 0`). See `website/AGENTS.md`.
- **Wheel:** Hatch `force-include` in `pyproject.toml` copies `tokens.css` and `fonts/` into `audera/ui/static/brand/`; `theme.py` resolves the vendored copy first, repo-root `brand/` as fallback for editable installs.
