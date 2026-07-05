# ADR 004: UX Optionality Feature Flags

**Date:** 2026-07-04
**Status:** Accepted

## Context

Some UX decisions in the streamer dashboard are genuine taste or workflow tradeoffs with no objectively correct answer — for example, whether an unselected player is represented as a mute checkbox or a disabled toggle. Historically these decisions shipped as a single guessed option, chosen by the team rather than the user. The goal is to let users pick between a small, fixed set of alternate UX experiences per feature at runtime, from the Settings tab, with no rebuild or redeploy required.

## Decisions

1. The catalog (`audera/ui/features.py`'s `FEATURES` list) is the single source of truth for which features and options exist. No feature or option may exist only inside conditional UI code.
2. `FF_*` constants name a specific *option value* within a feature, so call sites read as `flag_enabled(settings, key, FF_X)` — self-documenting at the point of use.
3. Every feature ships 2-3 options; the first is always the default. This bounds scope and guarantees zero-config usability. It is enforced by convention and a registry invariant test, rather than a separate `is_default` field.
4. Flags are user-selected and DAL-persisted (`Settings.features`), not environment/build-time — distinct from typical feature-flag systems. Every option is fully shipped code; the flag only picks which pre-built UX path renders.
5. `Settings` stores raw selections only, never a resolved default. Default resolution is the catalog's job (`features.selected()`), keeping the model a plain persistence container.
6. Any new UI feature is expected to ship with optionality by default: when an agent implements a UI feature with more than one defensible UX, it should propose the catalog entry (or ask which options to offer) rather than silently picking one.
7. When a call site resolves a flag into a local boolean, that variable is named identically to the `FF_*` constant it derives from (e.g. `FF_DISABLED_VS_MUTE = flag_enabled(settings, key, features.FF_DISABLED_VS_MUTE)`). This makes every flag-gated UI branch instantly recognizable as a feature-flag conditional. The `features.` module prefix keeps the constant (an option-value string) unambiguously distinct from the local boolean, so no shadowing confusion arises.

## Consequences

- Adding a third option to an existing feature needs no `Settings` schema change.
- Adding a new feature needs a new `Feature` entry, `FF_*` constant(s), and a rendering branch, but still no schema change, since `features` is already a generic `dict[str, str]`.
- Old `settings.json` files missing the `features` key keep loading correctly, defaulting to `{}`.
- Flags are per-installation, not per-user-account, since Audera has no multi-user auth.
- Agents proposing UI work default to raising optionality as a question up front, rather than treating a single UX as a foregone conclusion.
- Reviewers can locate every flag-conditional branch by searching for `FF_` in a rendering module, since the local resolution variable and the constant share that prefix.
