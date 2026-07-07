import json
import os

import audera.dal.settings as settings_dal
from audera.models.settings import Settings


def _settings(features: dict | None = None) -> Settings:
    return Settings(plexamp_host='localhost', snapserver_host='localhost', features=features or {})


def test_settings_create(audera_home):
    settings = _settings()
    settings_dal.create(settings)
    assert settings_dal.exists()


def test_settings_get(audera_home):
    settings = _settings()
    settings_dal.create(settings)

    result = settings_dal.get()
    assert result == settings


def test_settings_get_or_create_creates(audera_home):
    settings = _settings()
    assert not settings_dal.exists()

    settings_dal.get_or_create(settings)
    assert settings_dal.exists()


def test_settings_get_or_create_reads(audera_home):
    settings = _settings()
    settings_dal.create(settings)

    result = settings_dal.get_or_create(_settings())
    assert result == settings


def test_settings_update_changes_features(audera_home):
    settings = _settings()
    settings_dal.create(settings)

    updated = _settings(features={'player_selection': 'disabled'})
    settings_dal.update(updated)

    result = settings_dal.get()
    assert result.features == {'player_selection': 'disabled'}


def test_settings_features_round_trip(audera_home):
    settings = _settings(features={'player_selection': 'disabled', 'volume': 'db'})
    settings_dal.create(settings)

    result = settings_dal.get()
    assert result.features == {'player_selection': 'disabled', 'volume': 'db'}


def test_settings_features_default_empty(audera_home):
    settings = _settings()
    settings_dal.create(settings)

    result = settings_dal.get()
    assert result.features == {}


def test_settings_load_without_features_key_backward_compatible(audera_home):
    file_path = os.path.join(settings_dal.PATH, settings_dal.FILE_NAME)
    os.makedirs(settings_dal.PATH, exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump({'settings': {'plexamp_host': 'localhost', 'snapserver_host': 'localhost'}}, f)

    result = settings_dal.get()
    assert result.features == {}


def test_settings_delete(audera_home):
    settings = _settings()
    settings_dal.create(settings)
    settings_dal.delete()
    assert not settings_dal.exists()
