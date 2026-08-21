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

Per-role `font-variation-settings` live where they are used (`website/docs/stylesheets/extra.css` and `audera/ui/components/theme.py`).

## Quasar / NiceGUI color slots

| Quasar slot | Brand token |
|---|---|
| `primary` | `--ink` |
| `secondary` | `--ink-3` |
| `accent` | `--ink` |
| `positive` | `--up` |

Quasar's color API takes hex strings, not `var()`, so `audera/ui/components/theme.py` restates these token values as Python constants and must be kept in sync with `tokens.css` by hand. The paper background is applied as CSS (`background: var(--paper)` in `theme.py`), not a Quasar color slot.

## Consuming tokens

- **Apps (NiceGUI):** `theme.py` serves `tokens.css` and fonts via `app.add_static_files()` and maps tokens to `app.colors()`. See `audera/ui/AGENTS.md`.
- **Website (Zensical):** a build-time `cp brand/tokens.css website/docs/stylesheets/brand.css` (plus fonts); `extra.css` bridges tokens to Material's `--md-*` variables. See `website/AGENTS.md`.
- **Wheel:** Hatch `force-include` in `pyproject.toml` copies `tokens.css` and `fonts/` into `audera/ui/static/brand/`; `theme.py` resolves the vendored copy first, repo-root `brand/` as fallback for editable installs.
