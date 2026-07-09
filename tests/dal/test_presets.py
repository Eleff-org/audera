import json
import os

import audera.dal.dsp as dsp_dal
import audera.dal.presets as presets_dal
from audera.models.dsp import Band, DSPConfig, Preset


def _make_preset(id='p1', name='My preset') -> Preset:
    return Preset(
        id=id,
        name=name,
        bands=[
            Band(id='b1', type='Lowshelf', freq=90.0, gain=10.0, q=0.7),
            Band(id='b2', type='Highshelf', freq=8000.0, gain=6.0, q=0.7),
        ],
    )


def test_save_and_get_round_trip(audera_home):
    preset = _make_preset()
    presets_dal.save_preset(preset)

    result = presets_dal.get_all_presets()
    assert result == [preset]
    assert result[0].bands[0].type == 'Lowshelf'


def test_delete_removes_preset(audera_home):
    preset = _make_preset()
    presets_dal.save_preset(preset)
    presets_dal.delete_preset(preset.id)
    assert presets_dal.get_all_presets() == []


def test_delete_missing_is_noop(audera_home):
    # No inbound FK — deleting a non-existent preset can never orphan anything.
    presets_dal.delete_preset('does-not-exist')
    assert presets_dal.get_all_presets() == []


def test_get_all_presets_is_name_sorted(audera_home):
    presets_dal.save_preset(_make_preset(id='p1', name='Zeta'))
    presets_dal.save_preset(_make_preset(id='p2', name='alpha'))
    presets_dal.save_preset(_make_preset(id='p3', name='Mike'))

    names = [preset.name for preset in presets_dal.get_all_presets()]
    assert names == ['alpha', 'Mike', 'Zeta']  # case-insensitive


def test_malformed_preset_is_skipped(audera_home):
    good = _make_preset(id='good', name='Good')
    presets_dal.save_preset(good)
    with open(os.path.join(presets_dal.PATH, 'bad.json'), 'w') as f:
        f.write('{ not valid json')

    result = presets_dal.get_all_presets()
    assert result == [good]  # the malformed file is skipped, the good one still loads


def test_player_config_is_never_returned(audera_home):
    # A player config written to dsp/*.json lives one directory up from dsp/presets/,
    # so the preset namespace can never surface it.
    dsp_dal.create(DSPConfig(player_id='cfg1', bands=[Band(id='b1', freq=1000.0)]))
    assert presets_dal.get_all_presets() == []


def test_missing_dir_returns_empty(audera_home, monkeypatch):
    monkeypatch.setattr(presets_dal, 'PATH', os.path.join(str(audera_home), 'dsp', 'nonexistent'))
    assert presets_dal.get_all_presets() == []


def test_save_writes_wrapped_shape(audera_home):
    preset = _make_preset()
    presets_dal.save_preset(preset)
    with open(os.path.join(presets_dal.PATH, 'p1.json'), 'r') as f:
        data = json.load(f)
    assert set(data.keys()) == {'preset'}
    assert data['preset']['id'] == 'p1'
    assert data['preset']['name'] == 'My preset'
