"""Integration tests for the device setup UI."""

import pytest
from nicegui.testing import User

import audera.services.netifaces as netifaces_module
from audera import platform
from audera.services.ap import AccessPoint
from audera.ui.setup.pages import Page


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
