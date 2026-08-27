"""Integration tests for the device setup UI."""

import pytest
from nicegui.testing import User

import audera.services.netifaces as netifaces_module
from audera import platform
from audera.services.ap import AccessPoint
from audera.ui.setup.pages import _CAPTIVE_PROBE_SUCCESS, Page, _captive_response


@pytest.fixture
def setup_page(monkeypatch):
    """Returns the setup Page class with dietpi platform check and AP I/O bypassed."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')
    monkeypatch.setattr(AccessPoint, 'start', lambda self: None)
    monkeypatch.setattr(AccessPoint, 'stop', lambda self: None)

    async def _empty_networks(**_):
        return {}

    monkeypatch.setattr(netifaces_module, 'get_wifi_networks', _empty_networks)
    return Page


async def test_welcome_renders_streamer(setup_page, user: User):
    page = setup_page(role='streamer')
    page.load()
    await user.open('/')
    await user.should_see('Welcome')
    await user.should_see('Start')
    await user.should_see('streamer')


async def test_pages_carry_brand_stylesheet(setup_page, user: User):
    """Every setup page pulls the brand CSS via header.render() -> theme.apply_page()."""
    page = setup_page(role='streamer')
    page.load()
    for route in ('/', '/connect', '/finish'):
        client = await user.open(route)
        assert '/brand/tokens.css' in client.head_html


async def test_welcome_renders_player(setup_page, user: User):
    page = setup_page(role='player')
    page.load()
    await user.open('/')
    await user.should_see('Welcome')
    await user.should_see('Start')
    await user.should_see('player')


async def test_connect_renders(setup_page, user: User):
    page = setup_page(role='streamer')
    page.load()
    await user.open('/connect')
    await user.should_see('Connect to Wi-Fi')
    await user.should_see('Refresh')
    await user.should_see('Back')
    await user.should_see('Continue')


async def test_finish_renders_streamer(setup_page, user: User):
    page = setup_page(role='streamer')
    page.load()
    await user.open('/finish')
    await user.should_see('streamer')
    await user.should_see('audera.local')


async def test_finish_renders_player(setup_page, user: User):
    page = setup_page(role='player')
    page.load()
    await user.open('/finish')
    await user.should_see('player')
    await user.should_see('audera.local')


@pytest.mark.parametrize('path', list(_CAPTIVE_PROBE_SUCCESS))
def test_captive_probe_redirects_before_portal_opened(path):
    """Every probe 302s to `/` until the operator lands on the portal, so the OS opens it."""
    response = _captive_response(path, opened=False)
    assert response.status_code == 302
    assert response.headers['location'] == '/'


@pytest.mark.parametrize('path,status,body,media_type', [(p, *v) for p, v in _CAPTIVE_PROBE_SUCCESS.items()])
def test_captive_probe_returns_os_success_after_portal_opened(path, status, body, media_type):
    """Once opened, each probe returns its OS success sentinel so the phone validates the network."""
    response = _captive_response(path, opened=True)
    assert response.status_code == status
    assert response.body == body.encode()

    # A bare 204 carries no body and therefore no content-type; the others echo the OS sentinel.
    assert response.media_type == (None if status == 204 else media_type)


async def test_opening_portal_flips_captive_probes(setup_page, user: User):
    """Landing on `/` flips the shared instance so subsequent probes stop signalling a portal."""
    page = setup_page(role='streamer')
    assert page.portal_opened is False

    page.load()
    await user.open('/')
    await user.should_see('Welcome')
    assert page.portal_opened is True
