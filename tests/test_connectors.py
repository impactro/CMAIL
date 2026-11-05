import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from cmail import ConnectorConfig, ConnectorRegistry, CmailApi, Principal
from cmail.config import ConfigError
from helpers import config_payload, config


def document():
    entries = {}
    for key in ('first', 'second'):
        value = config_payload()
        value['state']['directory'] = 'security/cmail/accounts/' + key
        value['imap']['account'] = key + '@example.test'
        entries[key] = value
    return {'schemaVersion': '2.0', 'webmailConnectorId': 'first', 'connectors': entries}


def registry(tmp_path):
    selected = ConnectorConfig.from_mapping(document(), path=tmp_path/'cmail.json')
    return ConnectorRegistry(selected)


def principal(reg, key, owner='owner-a', capabilities=frozenset({'mail.read', 'mail.send'})):
    return reg.principal_for_owner(key, owner, capabilities)


def test_schema_is_pure_and_native_services_are_lazy_singletons(tmp_path):
    value = document()
    before = copy.deepcopy(value)
    selected = ConnectorConfig.from_mapping(value, path=tmp_path/'cmail.json')
    assert value == before and not (tmp_path/'security').exists()
    reg = ConnectorRegistry(selected)
    with ThreadPoolExecutor(max_workers=4) as pool:
        apis = list(pool.map(lambda _: reg._api('first'), range(12)))
    assert all(api is apis[0] for api in apis)
    assert reg._api('second').service.store.path != apis[0].service.store.path


@pytest.mark.parametrize('bad', ['', '../first', 'First', 'a/b', 'a:b', 'a'*65])
def test_connector_ids_reject_unsafe_or_ambiguous_names(tmp_path, bad):
    value = document()
    value['connectors'][bad] = value['connectors'].pop('first')
    with pytest.raises(ConfigError):
        ConnectorConfig.from_mapping(value, path=tmp_path/'cmail.json')


def test_rejects_shared_state_duplicate_mailbox_and_missing_webmail(tmp_path):
    for change in ('state', 'account', 'webmail', 'unknown'):
        value = document()
        if change == 'state':
            value['connectors']['second']['state']['directory'] = 'security/cmail/accounts/first'
        elif change == 'account':
            value['connectors']['second']['imap']['account'] = 'FIRST@example.test'
        elif change == 'webmail':
            value['webmailConnectorId'] = 'absent'
        else:
            value['secret'] = 'not accepted'
        with pytest.raises(ConfigError):
            ConnectorConfig.from_mapping(value, path=tmp_path/'cmail.json')


def test_same_provider_accounts_and_owners_do_not_share_drafts(tmp_path):
    reg = registry(tmp_path)
    first = reg.bind('first', principal(reg, 'first'))
    second = reg.bind('second', principal(reg, 'second'))
    other_owner = reg.bind('first', principal(reg, 'first', 'owner-b'))
    preview = first.prepare_send({'recipients': ['recipient@example.test'], 'subject': 'Synthetic', 'body': 'No real send'})
    assert preview['connectorId'] == 'first'
    for other in (second, other_owner):
        with pytest.raises(ValueError):
            other.execute_send(preview['draftId'], preview['confirmationToken'])
    # The legitimate claim is untouched by foreign attempts; no send is needed to prove this.
    with reg._api('first').service.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM mail_drafts').fetchone()[0] == 1


def test_oauth_two_mailboxes_same_provider_reject_foreign_principals_and_revoke(tmp_path):
    from cmail.service import MailService
    from cmail.auth import MicrosoftAuthService
    from helpers import FakeMail, FakeOAuthFactory, config_payload_v11
    value = document()
    for key in value['connectors']:
        cfg = config_payload_v11('microsoft')
        cfg['state'] = value['connectors'][key]['state']
        cfg['microsoft'].update(clientId='synthetic', tenantId='tenant',
            clientSecretFile='not-opened.txt', redirectUri='http://localhost/auth/callback', account=key+'@example.test')
        value['connectors'][key] = cfg
    reg = ConnectorRegistry(ConnectorConfig.from_mapping(value, path=tmp_path/'cmail.json'))
    identities = {}
    for key in ('first', 'second'):
        cfg = reg._configs[key]
        from cmail.store import Store
        store = Store(cfg.state_dir)
        auth = MicrosoftAuthService(cfg, store, client_factory=FakeOAuthFactory())
        service = MailService(cfg, auth=auth, graph_factory=lambda *args: FakeMail())
        reg._apis[key] = CmailApi(service)
        identities[key] = store.save_identity('tenant', key, key+'@example.test', key,
                                              owner_id='owner-a')
        cache = auth._identity_cache(identities[key]['id'])
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b'synthetic-cache-not-a-token')
    a = principal(reg, 'first')
    b = principal(reg, 'second')
    assert a.identity_id != b.identity_id
    assert reg.bind('first', a).folders()
    with pytest.raises(PermissionError):
        reg.bind('second', a)
    with pytest.raises(PermissionError):
        principal(reg, 'first', 'unbound-owner')
    bound = reg.bind('first', a)
    reg._api('first').service.store.set_connection_status(a.identity_id, 'revoked')
    with pytest.raises(PermissionError):
        bound.folders()
    assert reg.bind('second', b).folders()  # Revoking A does not disconnect B.


def test_binding_wrong_account_or_empty_capabilities_is_rejected(tmp_path):
    reg = registry(tmp_path)
    with pytest.raises(PermissionError):
        reg.bind('second', principal(reg, 'first'))
    with pytest.raises(PermissionError):
        reg.bind('first', Principal('local-demo', 'first@example.test', frozenset(), 'owner-a'))
    with pytest.raises(ValueError):
        reg.principal_for_owner('first', 'owner-a', frozenset())
    with pytest.raises(ValueError):
        reg.bind('unknown', principal(reg, 'first'))


def test_read_only_binding_cannot_prepare_or_gain_reader_capabilities(tmp_path):
    reg = registry(tmp_path)
    read = reg.bind('first', principal(reg, 'first', capabilities=frozenset({'mail.read'})))
    with pytest.raises(PermissionError):
        read.prepare_send({'recipients': ['a@example.test'], 'subject': 'S', 'body': 'B'})
    write = reg.bind('first', principal(reg, 'first', capabilities=frozenset({'mail.send'})))
    with pytest.raises(PermissionError):
        write.annotation_reader()


def test_legacy_adapter_preserves_service_identity_paths_and_configuration(tmp_path):
    selected = config(tmp_path)
    api = CmailApi.from_config(selected)
    original = selected.config_file.read_bytes()
    reg = ConnectorRegistry.from_legacy(api, connector_id='current')
    assert reg._api('current') is api
    assert reg.native_api('current') is api
    assert reg._api('current').service is api.service
    assert reg._configs['current'].state_dir == selected.state_dir
    assert selected.config_file.read_bytes() == original
    assert not (tmp_path/'security/cmail/accounts').exists()


def test_load_same_pointer_and_public_inventory_omit_private_data(tmp_path):
    (tmp_path/'.env').write_text('CMAIL_CONFIG_FILE=cmail.json\n', encoding='utf-8')
    (tmp_path/'cmail.json').write_text(json.dumps(document()), encoding='utf-8')
    reg = ConnectorRegistry(ConnectorConfig.load(tmp_path))
    inventory = reg.list_connectors({'first': principal(reg, 'first')})
    assert inventory == [{'connectorId': 'first', 'provider': 'demo',
                          'capabilities': ['mail.read', 'mail.send'], 'webmail': True}]
    assert str(tmp_path) not in json.dumps(inventory) and '@' not in json.dumps(inventory)


def test_packaged_example_has_native_valid_configurations():
    from importlib.resources import files
    example = files('cmail').joinpath('defaults/connectors.config.example.json')
    selected = ConnectorConfig.from_file(str(example))
    assert set(selected.connectors) == {'first', 'second'}
    assert all(c.mode == 'demo' for c in selected.connectors.values())
