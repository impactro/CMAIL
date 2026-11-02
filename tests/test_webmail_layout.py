from fastapi.testclient import TestClient
from cmail.web import create_app
from helpers import config


def test_full_webmail_and_focused_blocks_use_the_same_authenticated_api(tmp_path):
    app = create_app(config(tmp_path))
    with TestClient(app) as client:
        full = client.get('/')
        assert full.status_code == 200 and 'id="mail-navigation"' in full.text
        assert 'id="mail-reader"' in full.text and 'id="folders"' not in full.text
        assert 'mailbox-shell.mjs' in full.text
        reader = client.get('/?readerOnly=1&folder=INBOX&messageId=fixture')
        assert reader.status_code == 200 and 'id="messageActions"' in reader.text
        compose = client.get('/?composeOnly=1')
        assert compose.status_code == 200 and 'id="composeForm"' in compose.text
        assert 'Autenticação' not in reader.text or 'mailbox-shell.mjs' not in reader.text
        assert client.get('/api/messages').status_code == 200


def test_hosted_company_connection_uses_one_owner_for_two_people(tmp_path):
    from cmail.service import MailService
    selected = config(tmp_path)
    service = MailService(selected)
    seen = []
    def identity(request):
        seen.append(request.headers.get('X-Person'))
        return {'identifier': 'company:fixture', 'capabilities': ['mail.read','mail.manage','mail.send','lists.manage']}
    with TestClient(create_app(selected, service, principal_resolver=identity)) as client:
        for person in ['ana', 'bia']:
            response = client.get('/connection', headers={'X-Person': person})
            assert response.status_code == 200 and 'E-mail da empresa' in response.text
    assert set(seen) == {'ana', 'bia'}
