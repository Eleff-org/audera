"""The full-page parametric-EQ editor for a single player."""

import asyncio
import uuid
from typing import TYPE_CHECKING, Literal, get_args

from nicegui import ui

import audera
from audera.dal import dsp as dsp_dal
from audera.dal import presets as presets_dal
from audera.domains.dsp import auto_preamp_db, clone_bands, compile_pipeline, format_rew, loudness_preset, parse_rew
from audera.models.dsp import PASS_TYPES, Band, DSPConfig, Preset
from audera.ui import components
from audera.ui.streamer.pages._clients import _camilladsp, _snapserver

if TYPE_CHECKING:
    from audera.ui.streamer.pages import Page

# Derived from the model literal so the editor's type choices can never drift from
# `audera.models.dsp.Band`. Pass filters carry no gain, so their gain field is disabled
# (their membership is tested against the shared `PASS_TYPES` taxonomy).
_BAND_TYPES = list(get_args(Band.model_fields['type'].annotation))


def render(page: 'Page', player_id: str) -> None:
    """Renders the full-page parametric-EQ editor for a single player.

    Bands are the source of truth; they are compiled to a live CamillaDSP pipeline
    on Save. Per-page edit state lives in closures (not on `page`, which is shared
    across every connected client): `state['saved']` mirrors the persisted config and
    `state['staged']` is the working copy that is compiled, validated, and pushed on
    Save. Scalar field edits mutate a band in place and only recompute the dirty
    indicator, clip-safe pre-amp clamp, and live response chart; structural changes
    (add/delete/type/preset/reset) refresh the band table.
    """
    components.header.render(audera.NAME, 'Streamer')

    snap = _snapserver(page.settings)
    try:
        clients = snap.get_clients()
    except Exception:
        clients = []
    live = next((client for client in clients if client.id == player_id), None)

    if live is None:
        with ui.column().classes('w-full gap-2 p-4'):
            ui.link('‹ Players', '/')
            ui.label('Player not found or unreachable.').classes('text-gray-500')
        return

    # The config is keyed by the player's own id (`dsp/{player_id}.json` is the link),
    # so `live.id` is all that's needed to resolve it.
    saved = dsp_dal.get_or_create(DSPConfig(player_id=live.id))
    state = {'saved': saved, 'staged': saved.model_copy(deep=True)}

    def _dirty() -> bool:
        return state['staged'] != state['saved']

    def _mark_changed() -> None:
        """Clamps pre-amp to the clip-safe ceiling, then refreshes dirty state, chart, count."""
        clamped = min(state['staged'].preamp_db, auto_preamp_db(state['staged'].bands))
        if clamped != state['staged'].preamp_db:  # min is a fixpoint — converges in one pass
            state['staged'].preamp_db = clamped
            preamp_field.value = clamped
        dirty_label.set_visibility(_dirty())
        has_bands = bool(state['staged'].bands)  # chart only once a band exists
        chart.set_visibility(has_bands)
        chart_message.set_visibility(not has_bands)
        if has_bands:
            # `EChart.options` is a read-only view onto the live props dict; swap its
            # contents in place (the documented "change the options" push) and redraw.
            chart.options.clear()
            chart.options.update(components.response_plot.options(state['staged']))
            chart.update()
        count_label.set_text(f'Bands ({len(state["staged"].bands)})')

    def _on_preamp(e) -> None:
        if e.value is not None:
            state['staged'].preamp_db = float(e.value)
        _mark_changed()

    def _on_enabled(band: Band, value: bool) -> None:
        band.enabled = bool(value)
        _mark_changed()

    def _on_type(band: Band, value: str) -> None:
        # `value` is constrained to `_BAND_TYPES` by the select; the assignment is
        # unvalidated (Band sets no `validate_assignment`), so the literal narrows fine.
        band.type = value  # type: ignore
        _band_table.refresh()  # the gain field's enabled state depends on the type
        _mark_changed()

    def _on_freq(band: Band, value) -> None:
        if value is not None:
            band.freq = float(value)
        _mark_changed()

    def _on_gain(band: Band, value) -> None:
        if value is not None:
            band.gain = float(value)
        _mark_changed()

    def _on_q(band: Band, value) -> None:
        if value is not None:
            band.q = float(value)
        _mark_changed()

    def _add_band() -> None:
        state['staged'].bands.append(Band(id=uuid.uuid4().hex, type='Peaking', freq=1000.0, gain=0.0, q=0.707))
        _band_table.refresh()
        _mark_changed()

    def _remove_band(band: Band) -> None:
        state['staged'].bands = [b for b in state['staged'].bands if b.id != band.id]
        _band_table.refresh()
        _mark_changed()

    def _apply_preset(kind: Literal['loudness', 'flat']) -> None:
        if kind == 'loudness':
            state['staged'].bands.extend(loudness_preset())
        else:
            state['staged'].bands = []
        _band_table.refresh()
        _mark_changed()

    def _apply_saved_preset(preset: Preset) -> None:
        """Appends fresh clones of a saved preset's bands onto the staged config.

        Apply = append + clone (never replace); the clones carry fresh ids so their
        `audera_peq_<id>` filter names can't collide. Routing through `_mark_changed`
        re-clamps the pre-amp and redraws the chart over the merged set — same wiring
        as REW import.
        """
        state['staged'].bands.extend(clone_bands(preset.bands))
        _band_table.refresh()
        _mark_changed()

    def _delete_preset(preset: Preset) -> None:
        presets_dal.delete_preset(preset.id)
        _presets_menu.refresh()
        ui.notify(f'Deleted preset "{preset.name}"', type='positive', position='top-right')

    def _open_save_preset_dialog() -> None:
        """Opens a dialog to capture the current bands as a named, reusable preset."""
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Save preset').classes('font-medium text-lg mb-1')
            ui.label('Capture the current bands as a reusable preset you can append to any player.').classes(
                'text-xs text-gray-500 mb-2'
            )
            name_field = (
                ui.input('Preset name', placeholder='My preset')
                .props('outlined dense')
                .classes('w-full')
                .mark('preset-save-name')
            )

            def _on_save_preset() -> None:
                preset = Preset(
                    id=uuid.uuid4().hex,
                    name=(name_field.value or '').strip() or 'Untitled',
                    bands=clone_bands(state['staged'].bands),
                )
                presets_dal.save_preset(preset)
                _presets_menu.refresh()
                ui.notify(f'Saved preset "{preset.name}"', type='positive', position='top-right')
                dialog.close()

            with ui.row().classes('justify-between w-full mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat dense')
                ui.button('Save', on_click=_on_save_preset).props('dense').classes('bg-gray-800 text-white').mark(
                    'preset-save-run'
                )

        dialog.open()

    @ui.refreshable
    def _presets_menu() -> None:
        ui.menu_item('Loudness (seed bands)', on_click=lambda: _apply_preset('loudness')).mark('preset-loudness')
        ui.menu_item('Flat / clear all bands', on_click=lambda: _apply_preset('flat')).mark('preset-flat')
        saved = presets_dal.get_all_presets()
        if saved:
            ui.separator()
            for preset in saved:
                with ui.menu_item(on_click=lambda p=preset: _apply_saved_preset(p)).mark('preset-saved'):
                    with ui.row().classes('items-center justify-between w-full'):
                        ui.label(preset.name)
                        (
                            ui.button(icon='delete', on_click=lambda p=preset: _delete_preset(p))
                            .props('flat dense round size=sm')
                            .classes('text-gray-400')
                            .on('click.stop')  # .stop: delete doesn't also fire append
                        )
        ui.separator()
        ui.menu_item('Save current as preset…', on_click=_open_save_preset_dialog).mark('preset-save-as')

    def _open_import_dialog() -> None:
        """Opens a paste-import dialog that appends CamillaDSP YAML filters as bands.

        REW (v5.20.14+) exports its parametric EQ as CamillaDSP YAML — the same
        `filters:` shape our compiler emits — so its exports paste in directly. Import is
        append-only (it never replaces existing bands) and routes through `_mark_changed`,
        so the auto-ceiling re-clamps the pre-amp and the chart redraws over the merged
        band set. Unsupported filter types are surfaced in the notification rather than
        dropped.
        """
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Import CamillaDSP YAML').classes('font-medium text-lg mb-1')
            ui.label(
                'Paste a CamillaDSP YAML export (e.g. from REW). Biquad filters are appended to the current '
                'configuration; the pre-amp stays auto-protected.'
            ).classes('text-xs text-gray-500 mb-2')
            text = (
                ui.textarea(
                    placeholder='filters:\n  band_1:\n    type: Biquad\n    parameters:'
                    '\n      type: Peaking\n      freq: 1000\n      q: 1.41\n      gain: -3.0'
                )
                .props('outlined autogrow')
                .classes('w-full font-mono')
            )

            def _on_import() -> None:
                result = parse_rew(text.value or '')
                state['staged'].bands.extend(result.bands)
                _band_table.refresh()
                _mark_changed()  # re-clamps pre-amp + redraws chart over the merged bands
                message = f'Imported {len(result.bands)} band(s)'
                if result.skipped:
                    message += f', skipped {len(result.skipped)} filter(s)'
                ui.notify(message, type='positive', position='top-right')
                dialog.close()

            with ui.row().classes('justify-between w-full mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat dense')
                ui.button('Import', on_click=_on_import).props('dense').classes('bg-gray-800 text-white').mark(
                    'config-import-run'
                )

        dialog.open()

    def _open_export_dialog() -> None:
        """Opens a dialog showing the *saved* configuration as CamillaDSP YAML.

        The YAML carries the `filters:` tag REW (v5.20.14+) requires to re-import, so a
        round-trip out to REW and back is lossless. The text is always the saved config
        (never the staged edits): a partial edit would export a config that never
        clip-guarded, so Save is the gate. When the editor is dirty a banner spells this
        out; Copy and Download surface the same text.
        """
        yaml_text = format_rew(state['saved'].preamp_db, state['saved'].bands)
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Export CamillaDSP YAML').classes('font-medium text-lg mb-1')
            if _dirty():
                ui.label(
                    'There are unsaved changes. Export downloads only the saved configuration — '
                    'Save first to export the current editor contents.'
                ).classes('text-xs text-amber-500 mb-2').mark('export-unsaved-banner')
            ui.textarea(value=yaml_text).props('outlined readonly autogrow').classes('w-full font-mono')

            def _on_copy() -> None:
                ui.clipboard.write(yaml_text)  # synchronous in NiceGUI 3.11.1
                ui.notify('Copied to clipboard', type='positive', position='top-right')

            def _on_download() -> None:
                ui.download.content(yaml_text, f'{live.name}-dsp.yml')

            with ui.row().classes('justify-between w-full mt-2'):
                ui.button('Close', on_click=dialog.close).props('flat dense')
                ui.button('Copy', on_click=_on_copy).props('dense')
                ui.button('Download .yml', on_click=_on_download).props('dense').classes('bg-gray-800 text-white')

        dialog.open()

    def _on_reset() -> None:
        state['staged'] = state['saved'].model_copy(deep=True)
        preamp_field.value = state['staged'].preamp_db
        _band_table.refresh()
        _mark_changed()

    async def _on_save() -> None:
        """Compiles → validates → pushes the live pipeline, then persists the config.

        Pattern B (live apply, no restart): the daemon owns volume and `SetConfigJson`
        leaves the fader untouched, so no volume snapshot/restore is needed. The config
        is keyed by the player id (`dsp/{id}.json`), so Save only updates that one file.
        """
        camilla = _camilladsp(live.host)
        try:
            current = await asyncio.to_thread(camilla.get_config)
            compiled = compile_pipeline(current, state['staged'])
            await asyncio.to_thread(camilla.validate_config, compiled)  # gate; raises on invalid
            await asyncio.to_thread(camilla.set_config, compiled)
        except Exception as exc:
            ui.notify(f'Save failed: {exc}', type='negative', position='top-right')
            return
        await asyncio.to_thread(dsp_dal.update, state['staged'])
        try:
            await asyncio.to_thread(camilla.reset_clipped_samples)  # start the clip watch fresh
        except Exception:
            pass
        state['saved'] = state['staged'].model_copy(deep=True)
        _mark_changed()
        ui.notify('Saved', type='positive', position='top-right')

    async def _poll_clips() -> None:
        try:
            count = await asyncio.to_thread(_camilladsp(live.host).get_clipped_samples)
        except Exception:
            return
        if count:
            clip_label.set_text(f'⚠ {count} clipped samples')
            clip_label.set_visibility(True)
        else:
            clip_label.set_visibility(False)

    @ui.refreshable
    def _band_table() -> None:
        with ui.row(wrap=False).classes('items-center gap-2 w-full text-xs text-gray-500'):
            ui.label('On').classes('w-10 text-center')
            ui.label('Type').classes('w-32')
            ui.label('Freq (Hz)').classes('w-24')
            ui.label('Gain (dB)').classes('w-24')
            ui.label('Q').classes('w-20')
            ui.label('').classes('w-10')
        for band in state['staged'].bands:
            with ui.row(wrap=False).classes('items-center gap-2 w-full'):
                ui.checkbox(value=band.enabled, on_change=lambda e, b=band: _on_enabled(b, e.value)).classes('w-10')
                ui.select(_BAND_TYPES, value=band.type, on_change=lambda e, b=band: _on_type(b, e.value)).props(
                    'dense outlined'
                ).classes('w-32')
                ui.number(value=band.freq, step=1, format='%.0f', on_change=lambda e, b=band: _on_freq(b, e.value)).props(
                    'dense outlined debounce=200'
                ).classes('w-24')
                gain_field = (
                    ui.number(value=band.gain, step=0.1, format='%.1f', on_change=lambda e, b=band: _on_gain(b, e.value))
                    .props('dense outlined debounce=200')
                    .classes('w-24')
                )
                gain_field.set_enabled(band.type not in PASS_TYPES)
                ui.number(value=band.q, step=0.001, format='%.3f', on_change=lambda e, b=band: _on_q(b, e.value)).props(
                    'dense outlined debounce=200'
                ).classes('w-20')
                ui.button(icon='delete', on_click=lambda b=band: _remove_band(b)).props('flat dense round size=sm').classes(
                    'text-gray-400'
                )
        ui.button('+ Add band', on_click=_add_band).props('flat dense').classes('mt-2')

    with ui.row().classes('items-center justify-between w-full'):
        ui.label(f'{live.name} · Advanced DSP').classes('text-lg font-medium')
        ui.link('‹ Players', '/')

    with ui.column().classes('w-full gap-3'):
        with ui.row().classes('items-center gap-4 w-full'):
            preamp_field = (
                ui.number(
                    'Pre-amp (dB) · auto-protected',
                    value=state['staged'].preamp_db,
                    step=0.1,
                    format='%.1f',
                    on_change=_on_preamp,
                )
                .props('dense outlined')
                .classes('w-40')
            )
            with ui.button('Presets', icon='tune').props('flat dense'):
                with ui.menu():
                    _presets_menu()
            with ui.button('Config', icon='import_export').props('flat dense'):
                with ui.menu():
                    ui.menu_item('Import CamillaDSP YAML…', on_click=_open_import_dialog).mark('config-import')
                    ui.menu_item('Export CamillaDSP YAML…', on_click=_open_export_dialog).mark('config-export')
            ui.space()
            ui.button('Reset', on_click=_on_reset).props('flat dense')
            ui.button('Save', on_click=_on_save).props('dense').classes('bg-gray-800 text-white')

        # Persistent handle + empty-state message, both toggled by the forward-closure
        # `_mark_changed`: the chart shows only once a band exists, the message otherwise.
        chart = components.response_plot.render(state['staged'])
        chart_message = ui.label(
            'Add a band to see the live frequency-response curve — start from Presets ▾, or + Add band below.'
        ).classes('text-sm text-gray-500 p-4')

        _band_table()

        with ui.row().classes('items-center gap-4 w-full mt-2 text-xs text-gray-500'):
            count_label = ui.label()
            ui.label('IIR biquads · ~0% CPU')
            dirty_label = ui.label('Unsaved changes ●').classes('text-amber-500')
            clip_label = ui.label('').classes('text-red-500')
            clip_label.set_visibility(False)  # hidden until the clip poll reports a nonzero count

    _mark_changed()
    ui.timer(3.0, _poll_clips)
