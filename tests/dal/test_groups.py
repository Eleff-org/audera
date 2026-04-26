import audera.dal.groups as groups
from audera.models.player import Group


def _make_group(id='grp1', name='Living Room') -> Group:
    return Group(
        id=id,
        name=name,
        client_ids=[],
        stream_id='',
        muted=False,
        volume=100,
    )


def test_group_create(audera_home):
    group = _make_group()
    groups.create(group)
    assert groups.exists(group.id)


def test_group_get(audera_home):
    group = _make_group()
    groups.create(group)

    result = groups.get_group(group.id)
    assert result == group


def test_group_update(audera_home):
    group = _make_group()
    groups.create(group)

    updated = Group(
        id=group.id,
        name=group.name,
        client_ids=['client-a'],
        stream_id='stream-1',
        muted=True,
        volume=60,
    )
    groups.update(updated)

    result = groups.get_group(group.id)
    assert result.volume == 60
    assert result.muted is True
    assert result.stream_id == 'stream-1'


def test_group_delete(audera_home):
    group = _make_group()
    groups.create(group)
    groups.delete(group.id)
    assert not groups.exists(group.id)


def test_get_all_groups(audera_home):
    g1 = _make_group(id='g1', name='Kitchen')
    g2 = _make_group(id='g2', name='Bedroom')
    groups.create(g1)
    groups.create(g2)

    result = groups.get_all_groups()
    ids = {g.id for g in result}
    assert ids == {'g1', 'g2'}


def test_get_all_groups_empty(audera_home):
    result = groups.get_all_groups()
    assert result == []


def test_attach_client(audera_home):
    group = _make_group()
    groups.create(group)

    result = groups.attach_client(group.id, 'client-x')
    assert 'client-x' in result.client_ids

    on_disk = groups.get_group(group.id)
    assert 'client-x' in on_disk.client_ids


def test_attach_client_idempotent(audera_home):
    group = _make_group()
    groups.create(group)
    groups.attach_client(group.id, 'client-x')
    groups.attach_client(group.id, 'client-x')

    result = groups.get_group(group.id)
    assert result.client_ids.count('client-x') == 1


def test_detach_client(audera_home):
    group = Group(id='grp1', name='Test', client_ids=['client-x'], stream_id='', muted=False, volume=100)
    groups.create(group)

    groups.detach_client(group.id, 'client-x')
    result = groups.get_group(group.id)
    assert 'client-x' not in result.client_ids


def test_assign_stream(audera_home):
    group = _make_group()
    groups.create(group)

    groups.assign_stream(group.id, 'stream-abc')
    result = groups.get_group(group.id)
    assert result.stream_id == 'stream-abc'
