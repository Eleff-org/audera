"""Audera streamer dashboard pages"""

import asyncio
import os
import socket
import subprocess
import uuid
from importlib.metadata import version as _pkg_version
from typing import Literal, Optional, get_args

import httpx
from dotenv import load_dotenv
from nicegui import ui

import audera
from audera.clients import CamillaDSPClient, SnapserverClient
from audera.dal import dsp as dsp_dal
from audera.dal import players as players_dal
from audera.dal import presets as presets_dal
from audera.dal import settings as settings_dal
from audera.domains.dsp import auto_preamp_db, clone_bands, compile_pipeline, format_rew, loudness_preset, parse_rew
from audera.models.dsp import Band, Preset
from audera.models.settings import Settings
from audera.ui import components, features

load_dotenv()

# Derived from the model literal so the editor's type choices can never drift from
# `audera.models.dsp.Band`. Pass filters carry no gain, so their gain field is disabled.
_BAND_TYPES = list(get_args(Band.model_fields['type'].annotation))
_PASS_TYPES = {'Lowpass', 'Highpass'}

_PLEX_CLIENT_ID = str(uuid.uuid4())
_PLEX_HEADERS = {
    'X-Plex-Product': audera.NAME,
    'X-Plex-Version': _pkg_version('audera'),
    'X-Plex-Client-Identifier': _PLEX_CLIENT_ID,
    'X-Plex-Platform': 'Linux',
    'Accept': 'application/json',
}


def _load_settings() -> Settings:
    return settings_dal.get_or_create(
        Settings(
            plexamp_host=os.getenv('AUDERA_PLEXAMP_HOST', 'localhost'),
            snapserver_host=os.getenv('AUDERA_SNAPSERVER_HOST', 'localhost'),
            features=features.default_selections(),
        )
    )


def _snapserver(settings: Settings) -> SnapserverClient:
    return SnapserverClient(host=settings.snapserver_host, port=audera.SNAPSERVER_PORT)


def _camilladsp(host: str) -> CamillaDSPClient:
    """Returns a CamillaDSPClient for the given player host."""
    return CamillaDSPClient(host=host)


def _plexamp_state() -> Literal['inactive', 'unclaimed', 'claimed']:
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'plexamp'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip() != 'active':
            return 'inactive'
    except Exception:
        return 'inactive'
    try:
        with socket.create_connection(('127.0.0.1', audera.PLEXAMP_PORT), timeout=1):
            return 'claimed'
    except OSError:
        return 'unclaimed'


def _create_plex_pin() -> tuple[int, str]:
    resp = httpx.post(
        'https://plex.tv/api/v2/pins',
        params={'strong': 'true'},
        headers=_PLEX_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['id'], data['code']


def _poll_plex_pin(pin_id: int) -> Optional[str]:
    resp = httpx.get(
        f'https://plex.tv/api/v2/pins/{pin_id}',
        headers=_PLEX_HEADERS,
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json().get('authToken') or None


def _get_claim_token(auth_token: str) -> str:
    resp = httpx.get(
        'https://plex.tv/api/claim/token.json',
        headers={**_PLEX_HEADERS, 'X-Plex-Token': auth_token},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['token']


def _restart_plexamp_with_claim(claim_token: str) -> None:
    subprocess.run(['systemctl', 'stop', 'plexamp'], timeout=15, check=True)
    override_dir = '/etc/systemd/system/plexamp.service.d'
    os.makedirs(override_dir, exist_ok=True)
    with open(f'{override_dir}/claim.conf', 'w') as f:
        f.write(f'[Service]\nEnvironment=PLEXAMP_CLAIM_TOKEN={claim_token}\n')
    subprocess.run(['systemctl', 'daemon-reload'], timeout=10, check=True)
    subprocess.run(['systemctl', 'start', 'plexamp'], timeout=10, check=True)


def _remove_claim_override() -> None:
    override = '/etc/systemd/system/plexamp.service.d/claim.conf'
    if os.path.exists(override):
        os.remove(override)
    subprocess.run(['systemctl', 'daemon-reload'], timeout=10)


class Page:
    """A `class` that represents the streamer dashboard app."""

    def __init__(self):
        """Initializes an instance of the streamer dashboard app."""
        self.settings = _load_settings()
        self._client = _snapserver(self.settings)
        self._dialog_open: bool = False

    def load(self) -> None:
        """Registers page routes."""
        ui.page('/')(self.index)
        ui.page('/player/{player_id}/dsp')(self.dsp)

    def index(self) -> None:
        """Renders the main dashboard page."""
        components.header.render(audera.NAME, 'Streamer')

        with ui.tabs().classes('w-full') as tabs:
            players_tab = ui.tab('Players')
            services_tab = ui.tab('Services')
            settings_tab = ui.tab('Settings')

        with ui.tab_panels(tabs, value=players_tab).classes('w-full'):
            with ui.tab_panel(players_tab):
                self._build_players_tab()  # type: ignore
            with ui.tab_panel(services_tab):
                self._build_services_tab()  # type: ignore
            with ui.tab_panel(settings_tab):
                self._build_settings_tab()

        def _maybe_refresh():
            if not self._dialog_open:
                self._build_players_tab.refresh()

        ui.timer(10.0, _maybe_refresh)

    def dsp(self, player_id: str) -> None:
        """Renders the full-page parametric-EQ editor for a single player.

        Bands are the source of truth; they are compiled to a live CamillaDSP pipeline
        on Save. Per-page edit state lives in closures (not on `self`, which is shared
        across every connected client): `state['saved']` mirrors the persisted config and
        `state['staged']` is the working copy that is compiled, validated, and pushed on
        Save. Scalar field edits mutate a band in place and only recompute the dirty
        indicator, clip-safe pre-amp clamp, and live response chart; structural changes
        (add/delete/type/preset/reset) refresh the band table.
        """
        components.header.render(audera.NAME, 'Streamer')

        snap = _snapserver(self.settings)
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

        # `SnapserverClient.get_clients` always reports `dsp_id=''` (it has no view of the
        # persisted FK), so recover the link from the players DAL before resolving —
        # otherwise `resolve_for_player` would re-mint an orphan config on every open.
        persisted = players_dal.get(player_id) if players_dal.exists(player_id) else live
        saved = dsp_dal.resolve_for_player(persisted)
        # Clamp the baseline once so an over-hot legacy config opens clean, not falsely dirty.
        saved.preamp_db = min(saved.preamp_db, auto_preamp_db(saved.bands))
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
            """Opens a paste-import dialog that appends REW / Equalizer APO filters as bands.

            Import is append-only (it never replaces existing bands) and routes through
            `_mark_changed`, so the auto-ceiling re-clamps the pre-amp and the chart redraws
            over the merged band set. Unparseable lines are surfaced in the notification
            rather than dropped.
            """
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label('Import REW filters').classes('font-medium text-lg mb-1')
                ui.label(
                    'Paste a REW or Equalizer APO filter export. Bands are appended to the current configuration; '
                    'the pre-amp stays auto-protected.'
                ).classes('text-xs text-gray-500 mb-2')
                text = (
                    ui.textarea(placeholder='Filter 1: ON PK Fc 1000 Hz Gain -3.0 dB Q 1.41')
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
                        message += f', skipped {len(result.skipped)} line(s)'
                    ui.notify(message, type='positive', position='top-right')
                    dialog.close()

                with ui.row().classes('justify-between w-full mt-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat dense')
                    ui.button('Import', on_click=_on_import).props('dense').classes('bg-gray-800 text-white').mark(
                        'config-import-run'
                    )

            dialog.open()

        def _open_export_dialog() -> None:
            """Opens a dialog showing the *saved* configuration as re-importable REW text.

            The text is always the saved config (never the staged edits): a partial edit
            would export a config that never clip-guarded, so Save is the gate. When the
            editor is dirty a banner spells this out; Copy and Download surface the same text.
            """
            rew_text = format_rew(state['saved'].preamp_db, state['saved'].bands)
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label('Export REW filters').classes('font-medium text-lg mb-1')
                if _dirty():
                    ui.label(
                        'There are unsaved changes. Export downloads only the saved configuration — '
                        'Save first to export the current editor contents.'
                    ).classes('text-xs text-amber-500 mb-2').mark('export-unsaved-banner')
                ui.textarea(value=rew_text).props('outlined readonly autogrow').classes('w-full font-mono')

                def _on_copy() -> None:
                    ui.clipboard.write(rew_text)  # synchronous in NiceGUI 3.11.1
                    ui.notify('Copied to clipboard', type='positive', position='top-right')

                def _on_download() -> None:
                    ui.download.content(rew_text, f'{live.name}-dsp.txt')

                with ui.row().classes('justify-between w-full mt-2'):
                    ui.button('Close', on_click=dialog.close).props('flat dense')
                    ui.button('Copy', on_click=_on_copy).props('dense')
                    ui.button('Download .txt', on_click=_on_download).props('dense').classes('bg-gray-800 text-white')

            dialog.open()

        def _on_reset() -> None:
            state['staged'] = state['saved'].model_copy(deep=True)
            preamp_field.value = state['staged'].preamp_db
            _band_table.refresh()
            _mark_changed()

        async def _on_save() -> None:
            """Compiles → validates → pushes the live pipeline, then persists the config.

            Pattern B (live apply, no restart): the daemon owns volume and `SetConfigJson`
            leaves the fader untouched, so no volume snapshot/restore is needed. The
            `dsp_id` FK was already persisted by `resolve_for_player` at page load, so Save
            only updates the config file.
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
                    gain_field.set_enabled(band.type not in _PASS_TYPES)
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
                        ui.menu_item('Import REW…', on_click=_open_import_dialog).mark('config-import')
                        ui.menu_item('Export…', on_click=_open_export_dialog).mark('config-export')
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

    @ui.refreshable
    def _build_services_tab(self) -> None:
        """Renders the Services tab — shows PlexAmp status and a browser-based OAuth claiming flow."""
        state = _plexamp_state()

        with ui.card().classes('w-full mb-2'):
            with ui.row().classes('items-center justify-between w-full'):
                ui.label('PlexAmp Headless').classes('font-medium')
                if state == 'claimed':
                    ui.label('available').classes('text-sm text-green-500')
                elif state == 'unclaimed':
                    ui.label('setup required').classes('text-sm text-amber-500')
                else:
                    ui.label('inactive').classes('text-sm text-red-500')

            if state == 'claimed':
                ui.link('Open PlexAmp', 'https://plexamp.local').classes('text-sm mt-1')

            elif state == 'unclaimed':
                connect_btn = ui.button('Connect with Plex').classes('mt-2')
                status_label = ui.label('').classes('text-sm text-gray-500 mt-1')
                auth_link = ui.link("Didn't open? Click here to authorize with Plex", '#', new_tab=True).classes('text-sm mt-1')
                auth_link.set_visibility(False)

                async def _on_connect():
                    connect_btn.disable()
                    status_label.set_text('Opening Plex authorization…')

                    try:
                        pin_id, pin_code = await asyncio.to_thread(_create_plex_pin)
                    except Exception as exc:
                        status_label.set_text(f'Error: {exc}')
                        connect_btn.enable()
                        return

                    auth_url = (
                        f'https://app.plex.tv/auth/#!?clientID={_PLEX_CLIENT_ID}'
                        f'&code={pin_code}'
                        f'&context%5Bdevice%5D%5Bproduct%5D={audera.NAME}'
                    )
                    ui.navigate.to(auth_url, new_tab=True)
                    status_label.set_text('Waiting for Plex authorization…')
                    auth_link.props(f'href="{auth_url}"')
                    auth_link.set_visibility(True)

                    deadline = asyncio.get_event_loop().time() + 300  # 5-minute timeout
                    poll_timer: list[ui.timer] = []

                    async def _poll_auth():
                        if asyncio.get_event_loop().time() > deadline:
                            poll_timer[0].cancel()
                            status_label.set_text('Authorization timed out. Please try again.')
                            connect_btn.enable()
                            return

                        try:
                            auth_token = await asyncio.to_thread(_poll_plex_pin, pin_id)
                        except Exception:
                            return  # transient error; retry on next tick

                        if not auth_token:
                            return

                        poll_timer[0].cancel()
                        status_label.set_text('Authorized. Claiming PlexAmp…')

                        try:
                            claim_token = await asyncio.to_thread(_get_claim_token, auth_token)
                            await asyncio.to_thread(_restart_plexamp_with_claim, claim_token)
                        except Exception as exc:
                            status_label.set_text(f'Claim failed: {exc}')
                            connect_btn.enable()
                            return

                        status_label.set_text('PlexAmp restarting…')

                        port_deadline = asyncio.get_event_loop().time() + 120
                        port_timer: list[ui.timer] = []

                        async def _poll_port():
                            if asyncio.get_event_loop().time() > port_deadline:
                                port_timer[0].cancel()
                                _remove_claim_override()
                                status_label.set_text('PlexAmp did not come up in time. Check the service.')
                                connect_btn.enable()
                                return

                            if _plexamp_state() == 'claimed':
                                port_timer[0].cancel()
                                _remove_claim_override()
                                self._build_services_tab.refresh()

                        port_timer.append(ui.timer(2.0, _poll_port))

                    poll_timer.append(ui.timer(2.0, _poll_auth))

                connect_btn.on('click', _on_connect)

    @ui.refreshable
    def _build_players_tab(self) -> None:
        """Renders the Players tab — lists Snapcast clients with per-client volume and mute/enable controls."""
        snap = _snapserver(self.settings)
        try:
            clients = snap.get_clients()
        except Exception:
            clients = []

        connected_clients = [c for c in clients if c.connected]
        if not connected_clients:
            ui.label('No Snapcast clients found.').classes('text-gray-500')
            return

        # Named after the feature-flag constant so flag-gated UI is obvious to the reader.
        FF_DISABLED_VS_MUTE = features.flag_enabled(self.settings, features.PLAYER_SELECTION_KEY, features.FF_DISABLED_VS_MUTE)

        for client in connected_clients:
            minimized = FF_DISABLED_VS_MUTE and client.muted
            with ui.card().classes('w-full mb-2'):
                mute_cb = None
                with ui.row().classes('items-center justify-between w-full'):
                    with ui.row().classes('items-center gap-2'):
                        if FF_DISABLED_VS_MUTE:
                            ui.switch(value=not client.muted, on_change=lambda e, c=client: self._on_enabled_change(c, e.value))
                        # A disabled player is grayed out to reinforce the "disabled" state.
                        name_label = ui.label(client.name).classes('font-medium')
                        if minimized:
                            name_label.classes('text-gray-400')
                    with ui.row().classes('items-center gap-2'):
                        if not FF_DISABLED_VS_MUTE:
                            mute_cb = ui.checkbox(
                                'Mute', value=client.muted, on_change=lambda e, c=client: self._on_mute_change(c.id, e.value)
                            )
                        settings_btn = (
                            ui.button(on_click=lambda c=client: self._open_settings_dialog(c))
                            .props('icon=edit_square flat dense round size=sm')
                            .classes('text-gray-400')
                            .mark('player-settings')
                        )
                        # Disable the settings icon for a disabled player, matching the intent of "disable".
                        if minimized:
                            settings_btn.set_enabled(False)
                        dsp_btn = (
                            ui.button(on_click=lambda c=client: ui.navigate.to(f'/player/{c.id}/dsp'))
                            .props('icon=equalizer flat dense round size=sm')
                            .classes('text-gray-400')
                            .mark('player-dsp')
                        )
                        # A disabled player has no live pipeline to edit, so gray out its EQ icon too.
                        if minimized:
                            dsp_btn.set_enabled(False)

                if minimized:
                    continue

                with ui.row(wrap=False).classes('items-center gap-4 w-full'):
                    host = client.host
                    try:
                        init_vol = _camilladsp(host).get_percent_volume()
                    except Exception:
                        init_vol = CamillaDSPClient.DEFAULT_PERCENT_VOLUME
                    slider = self._build_volume_controls(client.id, init_vol, client.host)
                    if mute_cb is not None:
                        slider.bind_enabled_from(mute_cb, 'value', backward=lambda v: not v)

    async def _on_mute_change(self, client_id: str, muted: bool) -> None:
        """Handles the Mute checkbox in the card header for the default Player Selection experience.

        Does not refresh the Players tab afterward, so the volume slider keeps its live
        drag state — see `_reset_snap_volume` for the same rationale.
        """
        await asyncio.to_thread(_snapserver(self.settings).set_client_volume, client_id, 100, muted=muted)

    async def _on_enabled_change(self, client, enabled: bool) -> None:
        """Handles the 'disabled' Player Selection experience's enable/disable switch.

        Toggling off mutes the Snapcast client (the minimized-card state is derived from
        `client.muted` on the next render); toggling on unmutes it.
        """
        await asyncio.to_thread(_snapserver(self.settings).set_client_volume, client.id, 100, muted=not enabled)
        self._build_players_tab.refresh()

    def _open_settings_dialog(self, client) -> None:
        """Opens a settings popup for renaming, latency, and Snapcast volume reset."""
        self._dialog_open = True

        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Settings').classes('font-medium text-lg mb-2')

            name_input = ui.input('Name', value=client.name).classes('w-full')
            latency_input = ui.number('Latency (ms)', value=client.latency_ms, min=-500, max=500, step=1).classes('w-full')

            # Snapcast volume is a sidecar kept at 100/0; CamillaDSP controls actual loudness.
            snap_vol = client.volume
            with ui.row().classes('w-full items-start justify-between mt-2'):
                with ui.column().classes('gap-0'):
                    ui.label('Snapcast Volume').classes('text-xs')
                    current_vol_label = ui.label(f'Current Volume {snap_vol}%').classes('text-xs text-gray-500')
                ui.button('Reset', on_click=lambda c=client, lbl=current_vol_label: self._reset_snap_volume(c, lbl)).props(
                    'dense'
                ).classes('bg-gray-800 text-white')

            ui.separator().classes('mt-4 mb-2')
            with ui.column().classes('text-xs text-gray-500 gap-1'):
                ui.label(f'ID      {client.id}')
                ui.label(f'Host    {client.host}')
                ui.label(f'Group   {client.group_id or "—"}')

            with ui.row().classes('justify-between w-full mt-4'):

                def _on_cancel():
                    self._dialog_open = False
                    dialog.close()

                async def _on_save(c=client, ni=name_input, li=latency_input):
                    snap = _snapserver(self.settings)
                    if ni.value and ni.value != c.name:
                        snap.set_client_name(c.id, ni.value)
                        ui.notify(f'Renamed to "{ni.value}"', type='positive', position='top-right')
                    if int(li.value) != c.latency_ms:
                        snap.set_client_latency(c.id, int(li.value))
                        ui.notify(f'Latency set to {int(li.value)} ms', type='positive', position='top-right')

                    self._dialog_open = False
                    dialog.close()
                    self._build_players_tab.refresh()

                ui.button('Cancel', on_click=_on_cancel).props('flat dense')
                ui.button('Save', on_click=_on_save).props('dense').classes('bg-gray-800 text-white')

        dialog.on('hide', lambda: setattr(self, '_dialog_open', False))
        dialog.open()

    def _reset_snap_volume(self, client, vol_label=None) -> None:
        """Resets the Snapcast client volume to 100% / unmuted.

        If vol_label is provided (from the settings dialog), its text is updated to
        reflect the new value. The players tab is *not* refreshed so that the CamillaDSP
        volume sliders retain their current visual state.
        """
        _snapserver(self.settings).set_client_volume(client.id, 100, muted=False)
        if vol_label is not None:
            vol_label.set_text('Current Volume 100%')
        ui.notify('Snapcast volume reset to 100%', type='positive', position='top-right')

    def _build_volume_controls(
        self,
        client_id: str,
        initial_volume: float,
        client_host: str = '',
    ) -> ui.slider:
        """Renders a volume icon, slider, and live value label (routed through CamillaDSP).

        Volume is owned by the CamillaDSP daemon, which persists it durably via its
        `--statefile`; the slider seeds from the daemon (`get_percent_volume`) and writes
        through it (`set_percent_volume`) — the app keeps no replica.

        The slider is **always** a percent (0-100) control regardless of the 'volume'
        feature selection, so the handle sits at the same physical spot when toggling
        between modes. The selection only changes the value label: percent mode shows
        `NN%`, dB mode shows `percent_to_db(value)` as `-N.N dB`. Both modes drive
        CamillaDSP through `set_percent_volume`.

        Mute is anchored at the slider floor (`percent <= 0`, displayed as `MIN_DB` in dB
        mode), never on lossy zero-rounding, so a mid-range edit never silently mutes the
        client on the next refresh. The seed is step-aligned to the integer percent slider
        so the periodic refresh does not fire a phantom `update:model-value`.

        Returns the `ui.slider` element so the caller can bind its enabled state to the
        Mute checkbox built alongside it in the card header.
        """
        camilla = _camilladsp(client_host) if client_host else _camilladsp('localhost')
        # Named after the feature-flag constant so flag-gated UI is obvious to the reader.
        FF_VOLUME_PERC_OR_DB = features.flag_enabled(self.settings, features.VOLUME_KEY, features.FF_VOLUME_PERC_OR_DB)

        async def _persist_and_sync(percent: float) -> None:
            muted = percent <= 0
            await asyncio.to_thread(
                _snapserver(self.settings).set_client_volume,
                client_id,
                0 if muted else 100,
                muted=muted,
            )

        async def _on_volume_percent(e):
            percent = int(e.value)
            try:
                await asyncio.to_thread(camilla.set_percent_volume, percent)
            except Exception:
                pass
            await _persist_and_sync(percent)

        ui.icon('volume_up').classes('text-gray-400')
        slider = ui.slider(min=0, max=100, step=1, value=int(round(initial_volume)), on_change=_on_volume_percent).classes(
            'grow'
        )
        # Fixed width + right-align keeps the slider length constant as the label text
        # changes digit count (e.g. -9.0 dB -> -10.0 dB), so the handle doesn't shift.
        value_label = ui.label().classes('text-xs text-gray-500 shrink-0 whitespace-nowrap text-right w-16')
        if FF_VOLUME_PERC_OR_DB:
            value_label.bind_text_from(slider, 'value', backward=lambda v: f'{camilla.percent_to_db(v):.1f} dB')
        else:
            value_label.bind_text_from(slider, 'value', backward=lambda v: f'{int(v)}%')

        return slider

    def _build_settings_tab(self) -> None:
        """Renders the Settings tab — one single-select button group per registered UX feature."""
        ui.label('Features').classes('text-lg font-medium mb-2')
        for feature in features.FEATURES:
            ui.label(feature.label).classes('text-sm text-gray-500')
            ui.toggle(
                {option.value: option.label for option in feature.options},
                value=features.selected(self.settings, feature.key),
                on_change=lambda e, key=feature.key: self._on_feature_change(key, e.value),
            ).classes('mb-4')

    def _on_feature_change(self, key: str, value: str) -> None:
        """Persists a feature-flag selection and refreshes the Players tab to reflect it."""
        self.settings.features[key] = value
        settings_dal.save(self.settings)
        self._build_players_tab.refresh()
