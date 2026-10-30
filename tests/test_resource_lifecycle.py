"""Resource regressions: transactions, bounded previews and nonblocking HTTP."""
import io
import json
import re
import sqlite3
import threading
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from cmail.http_io import read_limited
from cmail.preview_cache import PreviewCache
from cmail.service import MailService
from cmail.store import Store
from cmail.web import create_app
from helpers import config


def test_sqlite_closes_after_commit_and_after_rollback(tmp_path):
    store = Store(tmp_path)
    with store.connect() as connection:
        connection.execute("INSERT INTO owner_preferences VALUES('committed',1,'now','now')")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with store.connect() as connection:
            connection.execute("INSERT INTO owner_preferences VALUES('rolled-back',1,'now','now')")
            raise RuntimeError('synthetic failure')
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    with store.connect() as connection:
        owners = [row[0] for row in connection.execute('SELECT owner_id FROM owner_preferences')]
    assert owners == ['committed']


def test_schema_is_initialized_once_and_database_recreation_is_detected(tmp_path):
    store = Store(tmp_path)
    initialize = Mock(wraps=store._database._initialize)
    store._database._initialize = initialize
    store.history('owner')
    store.history('owner')
    assert initialize.call_count == 1
    # A fresh synthetic database must still be initialized by the same instance.
    store.path.unlink()
    store.history('owner')
    assert initialize.call_count == 2


def test_concurrent_claim_has_exactly_one_winner(tmp_path):
    store = Store(tmp_path)
    draft = store.prepare({'recipients':['recipient@example.test'],'subject':'Test','body':'Synthetic'},'owner')
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=3)
        try:
            store.claim(draft['draftId'],draft['confirmationToken'],'owner')
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(),range(2)))
    assert sorted(results) == [False,True]


def test_expired_draft_state_is_committed_without_consuming_or_sending(tmp_path):
    store = Store(tmp_path)
    draft = store.prepare({'recipients':['recipient@example.test'],'subject':'Test','body':'Synthetic'},'owner')
    with store.connect() as connection:
        connection.execute("UPDATE mail_drafts SET expires_at='2000-01-01T00:00:00+00:00'")
    with pytest.raises(ValueError,match='expirada'):
        store.claim(draft['draftId'],draft['confirmationToken'],'owner')
    with store.connect() as connection:
        assert connection.execute('SELECT status FROM mail_drafts').fetchone()[0] == 'expired'


def test_history_query_uses_owner_index(tmp_path):
    store = Store(tmp_path)
    with store.connect() as connection:
        plan = connection.execute('EXPLAIN QUERY PLAN SELECT id FROM mail_audit_events '
                                  'WHERE owner_id=? ORDER BY id DESC LIMIT 50',('owner',)).fetchall()
    assert 'idx_mail_audit_owner_id' in str([tuple(row) for row in plan])


def test_preview_budget_is_in_bytes_and_owner_eviction_is_isolated():
    cache = PreviewCache(max_entries=5,max_bytes=20,max_entry_bytes=10,per_owner=1)
    other = cache.put('bob',b'12345')
    previous = cache.put('alice',b'12345')
    latest = cache.put('alice',b'67890')
    assert cache.get('alice',previous) is None
    assert cache.get('bob',other) == b'12345'
    assert cache.get('bob',latest) is None
    assert cache.stats()['bytes'] == 10
    with pytest.raises(ValueError):
        cache.put('alice','ação' * 3)  # UTF-8 bytes, not character count.


def test_preview_expiry_releases_bytes_on_reads_and_global_eviction_is_bounded():
    now = [0.0]
    cache = PreviewCache(max_entries=2,max_bytes=8,max_entry_bytes=8,per_owner=2,
                         ttl_seconds=10,clock=lambda:now[0])
    old = cache.put('alice',b'12345')
    fresh = cache.put('bob',b'67890')
    assert cache.get('alice',old) is None
    assert cache.get('bob',fresh) == b'67890'
    now[0] = 10
    assert cache.get('bob',fresh) is None
    assert cache.stats()['bytes'] == cache.stats()['entries'] == 0


def test_preview_cache_is_bounded_under_concurrent_writes():
    cache = PreviewCache(max_entries=8,max_bytes=80,max_entry_bytes=20,per_owner=2)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda n: cache.put(str(n % 4),b'1234567890'),range(100)))
    assert cache.stats()['entries'] <= 8
    assert cache.stats()['bytes'] <= 80


@pytest.mark.parametrize('operation',['read','send'])
def test_slow_provider_does_not_block_health_on_the_same_event_loop(tmp_path,operation):
    entered, release = threading.Event(), threading.Event()

    def block(*args,**kwargs):
        entered.set()
        assert release.wait(timeout=4), 'test did not release synthetic provider'
        return [] if operation == 'read' else {'accepted':True}

    provider = Mock()
    provider.folders.side_effect = block
    provider.send.side_effect = block
    service = MailService(config(tmp_path),provider)
    with TestClient(create_app(service.config,service)) as client, ThreadPoolExecutor(max_workers=2) as executor:
        page = client.get('/')
        headers = {'X-CSRF-Token':re.search(r'data-csrf="([^"]+)"',page.text).group(1)}
        if operation == 'read':
            request = lambda:client.get('/api/folders')
        else:
            draft = service.prepare({'recipients':['recipient@example.test'],'subject':'Test','body':'Synthetic'})
            request = lambda:client.post('/api/send/execute',headers=headers,
                json={'draftId':draft['draftId'],'confirmationToken':draft['confirmationToken'],'confirmed':True})
        slow = executor.submit(request)
        try:
            assert entered.wait(timeout=2)
            health = executor.submit(client.get,'/health').result(timeout=1)
            assert health.status_code == 200 and health.json()['ok']
            assert not slow.done()
        finally:
            release.set()
        assert slow.result(timeout=2).status_code == 200


def test_oversized_json_is_rejected_without_preparing_or_sending(tmp_path,monkeypatch):
    monkeypatch.setattr('cmail.web_context.MAX_REQUEST_BYTES',64)
    provider = Mock()
    service = MailService(config(tmp_path),provider)
    client = TestClient(create_app(service.config,service))
    page = client.get('/')
    headers = {'X-CSRF-Token':re.search(r'data-csrf="([^"]+)"',page.text).group(1)}
    response = client.post('/api/send/prepare',headers=headers,json={'body':'x'*80})
    assert response.status_code == 400 and 'oito MiB' in response.json()['error']
    assert service.store.status()['drafts'] == 0
    provider.send.assert_not_called()


def test_provider_reads_fail_explicitly_instead_of_silently_truncating():
    assert read_limited(io.BytesIO(b'1234'),4) == b'1234'
    with pytest.raises(ValueError,match='limite'):
        read_limited(io.BytesIO(b'12345'),4)


def test_public_imports_remain_compatible():
    from cmail import Principal, render_email_template
    from cmail.principal import Principal as CanonicalPrincipal
    from cmail.gmail import GoogleAuthService
    from cmail.google_auth import GoogleAuthService as CanonicalGoogleAuth
    from cmail.template_render import render_email_template as CanonicalRenderer
    assert Principal is CanonicalPrincipal
    assert GoogleAuthService is CanonicalGoogleAuth
    assert render_email_template is CanonicalRenderer


def test_python_facade_does_not_load_web_framework_until_requested():
    from helpers import PROJECT_ROOT
    script = (
        "import cmail,sys; assert 'fastapi' not in sys.modules; "
        "from cmail import create_api,Principal; assert callable(create_api); "
        "assert 'fastapi' not in sys.modules; "
        "assert 'create_app' in dir(cmail); from cmail import create_app; "
        "assert callable(create_app) and 'fastapi' in sys.modules"
    )
    subprocess.run([sys.executable,'-s','-B','-c',script],cwd=PROJECT_ROOT,check=True,
                   capture_output=True,text=True,timeout=15)
