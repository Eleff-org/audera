import os

import audera.dal.identities as identities
from audera.models.identity import Identity, generate_uuid_from_mac_address


def _make_identity(mac='aa:bb:cc:dd:ee:ff', address='192.168.1.10') -> Identity:
    return Identity(
        name='test-identity',
        uuid=generate_uuid_from_mac_address(mac),
        mac_address=mac,
        address=address,
    )


def test_identity_create_and_get(audera_home):
    identity = _make_identity()
    identities.create(identity)

    assert identities.exists()
    result = identities.get_identity()
    assert result.name == identity.name
    assert result.uuid == identity.uuid
    assert result.mac_address == identity.mac_address
    assert result.address == identity.address


def test_identity_delete(audera_home):
    identity = _make_identity()
    identities.create(identity)
    assert identities.exists()

    identities.delete()
    assert not identities.exists()


def test_identity_update_immutable_fields(audera_home):
    original = _make_identity()
    identities.create(original)

    updated = Identity(
        name='new-name',
        uuid='new-uuid',
        mac_address=original.mac_address,
        address=original.address,
    )
    result = identities.update(updated)

    assert result.name == original.name
    assert result.uuid == original.uuid


def test_identity_update_mutable_fields(audera_home):
    original = _make_identity()
    identities.create(original)

    new_mac = '11:22:33:44:55:66'
    new_address = '10.0.0.99'
    updated = Identity(
        name=original.name,
        uuid=original.uuid,
        mac_address=new_mac,
        address=new_address,
    )
    result = identities.update(updated)

    assert result.mac_address == new_mac
    assert result.address == new_address


def test_identity_get_or_create_creates_when_missing(audera_home):
    identity = _make_identity()
    assert not identities.exists()

    identities.get_or_create(identity)
    assert identities.exists()


def test_identity_get_or_create_reads_when_present(audera_home):
    identity = _make_identity()
    identities.create(identity)

    result_config = identities.get_or_create(identity)
    result = Identity.from_config(result_config)
    assert result == identity


def test_identity_file_on_disk(audera_home):
    identity = _make_identity()
    identities.create(identity)

    expected_path = os.path.join(str(audera_home), 'identity.json')
    assert os.path.isfile(expected_path)
