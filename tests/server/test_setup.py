"""Integration tests for audera.server.setup"""

import pytest

import audera.dal.identities as identities
from audera.models.identity import Identity, generate_uuid_from_mac_address
from audera.server.setup import Page

_MAC = 'aa:bb:cc:dd:ee:ff'


def _make_identity(name: str = 'test-player', mac: str = _MAC, address: str = '192.168.1.10') -> Identity:
    return Identity(
        name=name,
        uuid=generate_uuid_from_mac_address(mac),
        mac_address=mac,
        address=address,
    )


@pytest.fixture
def dietpi(monkeypatch):
    monkeypatch.setattr('audera.services.platform.NAME', 'dietpi')


@pytest.fixture
def mock_ap(monkeypatch):
    class _AP:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr('audera.ap.AccessPoint', _AP)


@pytest.fixture
def page(dietpi, mock_ap, audera_home):
    identity = _make_identity()
    identities.create(identity)
    return Page(identity, role='player')


def test_page_name_returns_identity_name(page):
    assert page.name == 'test-player'


def test_update_name_callback_persists_to_disk(page, monkeypatch):
    monkeypatch.setattr('nicegui.ui.notify', lambda *a, **kw: None)
    page.update_name_callback('Living Room')
    saved = identities.get_identity()
    assert saved.name == 'Living Room'


def test_update_name_callback_ignores_same_name(page, monkeypatch):
    notified = []
    monkeypatch.setattr('nicegui.ui.notify', lambda *a, **kw: notified.append(True))
    page.update_name_callback('test-player')
    assert not notified


def test_update_name_callback_ignores_none(page, monkeypatch):
    notified = []
    monkeypatch.setattr('nicegui.ui.notify', lambda *a, **kw: notified.append(True))
    page.update_name_callback(None)
    assert not notified


@pytest.mark.parametrize('role', ['player', 'streamer'])
def test_page_stores_role(dietpi, mock_ap, audera_home, role):
    identity = _make_identity()
    identities.create(identity)
    p = Page(identity, role=role)
    assert p.role == role
