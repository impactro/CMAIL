import base64
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail.annotation_reader import AnnotationReader
from cmail.gmail import GmailProvider
from cmail.principal import Principal, READ_MAIL


def test_owner_binding_is_read_only_and_rejects_rebind():
    identity = ['first']
    calls = []
    def principal(owner, capabilities):
        assert capabilities == frozenset({READ_MAIL})
        calls.append(owner)
        return Principal(identity[0], 'reader@example.test', capabilities, owner)
    provider = SimpleNamespace(annotation_page=lambda **args: {'items': [], 'nextCursor': 'next'})
    api = SimpleNamespace(principal_for_owner=principal,
        service=SimpleNamespace(config=SimpleNamespace(mode='gmail'), provider_for=lambda p: provider))
    reader = AnnotationReader(api, 'native-owner')
    assert reader.page(since='2026-11-02T00:00:00+00:00', until='2026-11-03T00:00:00+00:00')['nextCursor'] == 'next'
    assert len(reader.account_id) == 64 and 'reader@' not in reader.account_id
    identity[0] = 'second'
    with pytest.raises(PermissionError, match='ACCOUNT_CHANGED'):
        reader.page(since='2026-11-02T00:00:00+00:00', until='2026-11-03T00:00:00+00:00')
    assert set(calls) == {'native-owner'}


def test_physical_mailbox_key_detects_alias_without_changing_existing_cursor_id():
    import hashlib,json
    def reader(identity_id):
        api = SimpleNamespace(principal_for_owner=lambda owner,caps: Principal(identity_id,'same@example.test',caps,owner),
            service=SimpleNamespace(config=SimpleNamespace(mode='gmail'),
                store=SimpleNamespace(identity=lambda _: {'tenant_id':'google','subject_id':'verified-subject'})))
        return AnnotationReader(api,'owner')
    a,b=reader('local-id-one'),reader('local-id-two')
    assert a.account_id != b.account_id and a.mailbox_id == b.mailbox_id
    assert a.account_id == hashlib.sha256(json.dumps(['gmail','owner','local-id-one','same@example.test']).encode()).hexdigest()


