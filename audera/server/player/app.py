""" Audera player NiceGUI webserver """

import yaml
from nicegui import ui

import audera
from audera.dal import dsp as dsp_dal
from audera.dal import identities as identities_dal
from audera.services.camilladsp import CamillaDSPClient


def _camilladsp(host: str = 'localhost') -> CamillaDSPClient:
    return CamillaDSPClient(host=host, port=audera.CAMILLADSP_PORT)


def _get_player_id() -> str:
    try:
        identity = identities_dal.get_identity()
        return identity.uuid
    except Exception:
        return 'local'


@ui.page('/')
def index():
    player_id = _get_player_id()

    with ui.header().classes('bg-primary text-white items-center'):
        ui.label(audera.NAME).classes('text-xl font-bold')
        ui.label('Player — DSP').classes('text-sm ml-2 opacity-75')

    with ui.column().classes('w-full max-w-3xl mx-auto p-4 gap-4'):
        ui.label('DSP Pipeline Configuration').classes('text-lg font-semibold')

        try:
            dsp_config = dsp_dal.get_or_create(
                audera.models.dsp.DSPConfig(
                    id=player_id,
                    player_id=player_id,
                )
            )
            pipeline_yaml = yaml.dump(dsp_config.pipeline, default_flow_style=False) if dsp_config.pipeline else ''
        except Exception:
            dsp_config = None
            pipeline_yaml = ''

        editor = ui.textarea(
            label='Pipeline (YAML)',
            value=pipeline_yaml,
        ).classes('w-full font-mono').props('rows=20')

        enabled_toggle = ui.checkbox(
            'Enable DSP pipeline',
            value=dsp_config.enabled if dsp_config else True,
        )

        status_label = ui.label('').classes('text-sm')

        def apply():
            try:
                pipeline = yaml.safe_load(editor.value) or {}
                client = _camilladsp()
                client.set_config(pipeline)

                from audera.models import dsp as dsp_model
                new_config = dsp_model.DSPConfig(
                    id=player_id,
                    player_id=player_id,
                    pipeline=pipeline,
                    enabled=enabled_toggle.value,
                )
                dsp_dal.save(new_config)
                status_label.set_text('Applied successfully.')
                status_label.classes('text-green-600', remove='text-red-600')
            except Exception as e:
                status_label.set_text('Error: %s' % str(e))
                status_label.classes('text-red-600', remove='text-green-600')

        def reload_from_device():
            try:
                client = _camilladsp()
                pipeline = client.get_config()
                editor.set_value(yaml.dump(pipeline, default_flow_style=False) if pipeline else '')
                status_label.set_text('Loaded from device.')
                status_label.classes('text-blue-600', remove='text-red-600 text-green-600')
            except Exception as e:
                status_label.set_text('Error: %s' % str(e))
                status_label.classes('text-red-600', remove='text-blue-600 text-green-600')

        with ui.row().classes('gap-2'):
            ui.button('Apply', on_click=apply).props('color=primary')
            ui.button('Reload from device', on_click=reload_from_device).props('flat')


def run():
    """ Starts the Audera player NiceGUI webserver. """
    ui.run(host='0.0.0.0', port=audera.SERVER_PORT, title=audera.NAME, reload=False)
