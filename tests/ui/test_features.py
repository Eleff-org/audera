from audera.models.settings import Settings
from audera.ui import features


def _settings(features: dict | None = None) -> Settings:
    return Settings(plexamp_host='localhost', snapserver_host='localhost', features=features or {})


def test_features_registry_has_at_least_two_options_each():
    for feature in features.FEATURES:
        assert len(feature.options) >= 2


def test_features_registry_has_no_duplicate_keys():
    keys = [feature.key for feature in features.FEATURES]
    assert len(keys) == len(set(keys))


def test_features_registry_has_no_duplicate_option_values_within_feature():
    for feature in features.FEATURES:
        values = [opt.value for opt in feature.options]
        assert len(values) == len(set(values))


def test_feature_default_is_first_option():
    for feature in features.FEATURES:
        assert feature.default == feature.options[0]


def test_get_feature_returns_registered_feature():
    result = features.get_feature(features.PLAYER_SELECTION_KEY)
    assert result.key == features.PLAYER_SELECTION_KEY


def test_get_feature_raises_keyerror_for_unknown_key():
    try:
        features.get_feature('does_not_exist')
        assert False, 'expected KeyError'
    except KeyError:
        pass


def test_default_selections_covers_all_features():
    result = features.default_selections()
    assert set(result.keys()) == {feature.key for feature in features.FEATURES}


def test_default_selections_uses_first_option_value():
    result = features.default_selections()
    assert result[features.PLAYER_SELECTION_KEY] == 'mute'
    assert result[features.VOLUME_KEY] == 'percent'


def test_selected_returns_default_when_settings_features_empty():
    settings = _settings()
    assert features.selected(settings, features.PLAYER_SELECTION_KEY) == 'mute'


def test_selected_returns_default_when_key_missing():
    settings = _settings(features={'volume': 'db'})
    assert features.selected(settings, features.PLAYER_SELECTION_KEY) == 'mute'


def test_selected_returns_persisted_value_when_present():
    settings = _settings(features={'player_selection': 'disabled'})
    assert features.selected(settings, features.PLAYER_SELECTION_KEY) == 'disabled'


def test_flag_enabled_true_for_matching_selection():
    settings = _settings(features={'player_selection': 'disabled'})
    assert features.flag_enabled(settings, features.PLAYER_SELECTION_KEY, features.FF_DISABLED_VS_MUTE) is True


def test_flag_enabled_false_for_non_matching_selection():
    settings = _settings(features={'player_selection': 'mute'})
    assert features.flag_enabled(settings, features.PLAYER_SELECTION_KEY, features.FF_DISABLED_VS_MUTE) is False


def test_flag_enabled_false_when_unset_uses_default():
    settings = _settings()
    assert features.flag_enabled(settings, features.PLAYER_SELECTION_KEY, features.FF_DISABLED_VS_MUTE) is False


def test_option_resolves_unknown_value_to_default():
    feature = features.get_feature(features.PLAYER_SELECTION_KEY)
    assert feature.option('does_not_exist') == feature.default


def test_default_selections_includes_dsp_band_editor_full():
    assert features.default_selections()[features.DSP_BAND_EDITOR_KEY] == features.FF_DSP_BAND_EDITOR_FULL


def test_dsp_band_editor_has_three_options():
    feature = features.get_feature(features.DSP_BAND_EDITOR_KEY)
    assert [opt.value for opt in feature.options] == ['full', 'expand', 'dialog']
