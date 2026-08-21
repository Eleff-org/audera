"""How a settings file resolves against the feature registry.

Only the resolution rules are asserted here. What each option renders belongs with the Settings
tab, and the registry's shape is not restated.

Every case below is a settings file that already exists on a device. `default_selections()` runs
only when `settings.json` is first created, so a file written before a feature existed carries no
key for it, and a file written before an option was renamed carries a value nothing matches.
"""

from audera.models.settings import Settings
from audera.ui import features


def _settings(features: dict | None = None) -> Settings:
    return Settings(plexamp_host='localhost', snapserver_host='localhost', features=features or {})


def test_selected_returns_the_persisted_value():
    settings = _settings(features={'player_selection': 'disabled'})
    assert features.selected(settings, features.PLAYER_SELECTION_KEY) == 'disabled'


def test_selected_falls_back_to_the_default_when_nothing_is_persisted():
    assert features.selected(_settings(), features.PLAYER_SELECTION_KEY) == 'mute'


def test_selected_falls_back_to_the_default_when_another_feature_is_persisted():
    # A settings file carrying one feature's key and not another's, as on any device upgraded
    # across a release that added a feature.
    settings = _settings(features={'volume': 'db'})
    assert features.selected(settings, features.PLAYER_SELECTION_KEY) == 'mute'


def test_player_grouping_resolves_to_by_player_when_the_key_predates_the_feature():
    settings = _settings(features={'player_selection': 'disabled'})
    assert features.selected(settings, features.PLAYER_GROUPING_KEY) == features.FF_GROUPING_BY_PLAYER


def test_option_resolves_an_unmatched_value_to_the_default():
    # `option()` is the normalizer `selected()` routes an unmatched value through — it maps any
    # value nothing matches back onto the default option.
    feature = features.get_feature(features.PLAYER_SELECTION_KEY)
    assert feature.option('does_not_exist') == feature.default


def test_selected_normalizes_a_retired_persisted_value_to_the_default():
    # A value persisted for a since-retired option must resolve to the default rather than leak out
    # raw, so `flag_enabled` compares against a real option and never a stale one.
    settings = _settings(features={features.PLAYER_SELECTION_KEY: 'RETIRED_XYZ'})
    default = features.get_feature(features.PLAYER_SELECTION_KEY).default.value

    assert features.selected(settings, features.PLAYER_SELECTION_KEY) == default
    assert features.flag_enabled(settings, features.PLAYER_SELECTION_KEY, default) is True
