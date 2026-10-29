"""Stationery/signature inheritance, isolation and frozen outgoing previews."""
import base64
import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from cmail.appearance import Appearance, preview_html
from cmail.service import MailService, Principal, READ_MAIL, SEND_MAIL
from cmail.web import create_app
from test_cmail import config
from test_inline_images import PNG, image


def write_profile(root, value):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'profile.json').write_text(json.dumps(value), encoding='utf-8')


def test_independent_signature_and_template_combinations(tmp_path):
    appearance = Appearance(tmp_path, tmp_path / 'state')
    for template, signature in [('none','none'), ('default','none'), ('none','default'), ('default','default')]:
        packet = appearance.render('alice','Reunião','Olá, <equipe>',
            identity={'sender_name':'Alice & Bob'}, choices={'template':template,'signature':signature})
        assert ('<table' in packet['bodyHtml']) == (template != 'none')
        assert ('Alice &amp; Bob' in packet['bodyHtml']) == (signature != 'none')
        assert packet['bodyHtml'].count('Alice &amp; Bob') <= 1
        assert '&lt;equipe&gt;' in packet['bodyHtml']
        assert 'Olá, <equipe>' in packet['body']


def test_company_inheritance_tracks_changes_without_copying_to_user(tmp_path):
    appearance = Appearance(tmp_path, tmp_path / 'state')
    profile = {'fields':{'company_name':'Empresa A'},'modes':{'new':{'signature':'none'}}}
    write_profile(appearance.company_root, profile)
    assert appearance.settings('alice')['profile'] == {}
    assert 'Empresa A' in appearance.render('alice','Título','Texto')['bodyHtml']
    profile['fields']['company_name'] = 'Empresa B'
    write_profile(appearance.company_root, profile)
    assert 'Empresa B' in appearance.render('alice','Título','Texto')['bodyHtml']
    appearance.save('alice', {'fields':{'company_name':'Minha escolha'}})
    assert 'Minha escolha' in appearance.render('alice','Título','Texto')['bodyHtml']
    assert 'Empresa B' in appearance.render('bob','Título','Texto')['bodyHtml']
    appearance.save('alice', {})
    assert 'Empresa B' in appearance.render('alice','Título','Texto')['bodyHtml']


def test_modes_custom_signature_and_missing_signature_slot(tmp_path):
    appearance = Appearance(tmp_path, tmp_path / 'state')
    profile = {'signatureHtml':'<strong>{{sender_name}}</strong>',
               'templateHtml':'<article>{{body_html}}</article>',
               'modes':{'new':{'template':'custom','signature':'custom'}}}
    # Unsupported active/unknown structures fail explicitly; email tables/divs are supported.
    with pytest.raises(ValueError):
        appearance.save('alice',profile)
    profile['templateHtml'] = '<div>{{body_html}}</div>'
    appearance.save('alice',profile)
    assert appearance.render('alice','Título','Texto',identity={'sender_name':'Alice'})['bodyHtml'].count('Alice') == 1
    reply = appearance.render('alice','Re: Título','Texto',kind='reply')
    assert '<table' not in reply['bodyHtml']
    profile['templateHtml'] = '{{body_html}}{{signature_html}}{{signature_html}}'
    with pytest.raises(ValueError, match='uma vez'):
        appearance.save('alice',profile)


@pytest.mark.parametrize('source',[
    '<script>alert(1)</script>{{body_html}}', '<img src="cid:logo" onerror="alert(1)">{{body_html}}',
    '<a href="javascript:alert(1)">Link</a>{{body_html}}',
    '<div style="background:url(https://example.test)">{{body_html}}</div>',
    '<iframe src="https://example.test"></iframe>{{body_html}}',
    '<meta http-equiv="refresh" content="0;url=https://example.test">{{body_html}}',
    '<img src="file:///C:/private.png">{{body_html}}', '{{body_html.__class__}}',
    '{{body_html}}{{body_html}}', '<img src="https://example.test/tracker.png">{{body_html}}',
])
def test_untrusted_template_cannot_execute_or_load_external_content(tmp_path, source):
    appearance = Appearance(tmp_path, tmp_path / 'state')
    with pytest.raises(ValueError):
        appearance.save('alice', {'templateHtml':source,'modes':{'new':{'template':'custom'}}})
    assert not (appearance.user_root('alice') / 'profile.json').exists()


def test_local_html_and_logo_render_to_cid_and_frozen_bytes(tmp_path):
    appearance = Appearance(tmp_path, tmp_path / 'state')
    root = appearance.user_root('alice'); root.mkdir(parents=True)
    (root / 'signature.html').write_text('<strong>{{sender_name}}</strong><img src="cid:logo">',encoding='utf-8')
    (root / 'logo.png').write_bytes(PNG)
    profile = {'signatureFile':'signature.html','fields':{'sender_name':'Alice'},
               'assets':[{'contentId':'logo','file':'logo.png'}],
               'modes':{kind:{'signature':'custom'} for kind in ['new','reply','forward']}}
    appearance.save('alice',profile)
    packet = appearance.render('alice','Título','Texto')
    assert 'src="cid:logo"' in packet['bodyHtml']
    assert base64.b64decode(packet['inlineImages'][0]['contentBase64']) == PNG
    assert 'src="data:image/png;base64,' in preview_html(packet)
    (root / 'logo.png').write_bytes(b'invalid')
    with pytest.raises(ValueError):
        appearance.render('alice','Título','Texto')
    assert base64.b64decode(packet['inlineImages'][0]['contentBase64']) == PNG


@pytest.mark.parametrize('name',['../outside.html','C:/private.html','sub/../../outside.html'])
def test_file_paths_cannot_escape_personal_workspace(tmp_path, name):
    appearance = Appearance(tmp_path, tmp_path / 'state')
    with pytest.raises(ValueError):
        appearance.save('alice',{'signatureFile':name,'modes':{'new':{'signature':'custom'}}})


def test_authenticated_owner_and_capabilities_control_personal_files(tmp_path):
    service = MailService(config(tmp_path))
    alice = Principal('id-a','alice@example.test',frozenset({SEND_MAIL}),'workspace-a')
    bob = Principal('id-b','bob@example.test',frozenset({SEND_MAIL}),'workspace-b')
    service.save_appearance(alice,{'fields':{'sender_name':'Alice'}})
    assert service.appearance_settings(bob)['profile'] == {}
    with pytest.raises(PermissionError):
        service.save_appearance(Principal('','','', 'workspace-a'),{})


def test_draft_uses_prepared_appearance_after_company_and_user_changes(tmp_path):
    provider = Mock(); provider.send.return_value = {'accepted':True}
    service = MailService(config(tmp_path), provider)
    principal = Principal.local_operator()
    service.save_appearance(principal, {'fields':{'sender_name':'Antes'}})
    prepared = service.prepare({'recipients':['test@example.test'],'subject':'Título','body':'Olá',
                                'appearance':{}},principal)
    assert provider.send.call_count == 0
    service.save_appearance(principal, {'fields':{'sender_name':'Depois'}})
    service.execute(prepared['draftId'],prepared['confirmationToken'],principal)
    assert 'Antes' in provider.send.call_args.kwargs['body_html']
    assert 'Depois' not in provider.send.call_args.kwargs['body_html']
    with pytest.raises(ValueError):
        service.execute(prepared['draftId'],prepared['confirmationToken'],principal)
    assert provider.send.call_count == 1


def test_api_preview_is_owner_scoped_csrf_protected_and_does_not_prepare_or_send(tmp_path):
    service = MailService(config(tmp_path))
    owner = ['alice']
    resolver = lambda request: {'identifier':owner[0], 'email':owner[0]+'@example.test','capabilities':[READ_MAIL,SEND_MAIL]}
    client = TestClient(create_app(service.config,service,principal_resolver=resolver,url_prefix='/cm/cmail'))
    page = client.get('/cm/cmail/')
    token = re.search(r'data-csrf="([^"]+)"', page.text).group(1)
    headers = {'X-CSRF-Token':token}
    assert client.put('/cm/cmail/api/appearance',json={}).status_code == 403
    result = client.post('/cm/cmail/api/appearance/preview',headers=headers,
                         json={'subject':'Título','body':'Olá','profile':{'fields':{'sender_name':'Alice'}}})
    assert result.status_code == 200
    url = result.json()['previewUrl']
    preview = client.get(url)
    assert 'Alice' in preview.text and "default-src 'none'" in preview.headers['content-security-policy']
    assert 'sandbox' in preview.headers['content-security-policy']
    assert service.store.status('alice')['drafts'] == 0
    owner[0] = 'bob'
    assert client.get(url).status_code == 404
    assert client.get('/cm/cmail/api/appearance').json()['profile'] == {}


def test_reply_draft_freezes_new_content_and_single_execution(tmp_path):
    provider = Mock()
    provider.message.return_value = {'subject':'Original','from':{'address':'sender@example.test'},
                                     'to':[],'cc':[]}
    provider.reply.return_value = {'accepted':True}
    service = MailService(config(tmp_path),provider)
    principal = Principal.local_operator()
    service.save_appearance(principal,{'fields':{'sender_name':'Assinatura anterior'}})
    prepared = service.prepare_message_action(principal,'id-1',{'kind':'reply','body':'Resposta','appearance':{}})
    assert '<table' not in prepared['preview']['bodyHtml']
    service.save_appearance(principal,{'fields':{'sender_name':'Alterada'}})
    service.execute(prepared['draftId'],prepared['confirmationToken'],principal)
    assert 'Assinatura anterior' in provider.reply.call_args.kwargs['body_html']
    assert provider.reply.call_args.kwargs['reply_recipients'] == ['sender@example.test']
    assert provider.reply.call_count == 1


def test_invalid_unused_image_is_rejected_before_save(tmp_path):
    appearance = Appearance(tmp_path,tmp_path / 'state')
    with pytest.raises(ValueError):
        appearance.save('alice',{'assets':[image(raw=b'not-an-image')]})


def test_uploaded_logo_is_saved_as_file_and_used_by_default_signature(tmp_path):
    appearance = Appearance(tmp_path,tmp_path / 'state')
    result = appearance.save('alice',{'assets':[image('logo')]})
    saved = result['profile']['assets'][0]
    assert 'contentBase64' not in saved
    assert (appearance.user_root('alice') / saved['file']).read_bytes() == PNG
    packet = appearance.render('alice','Título','Texto')
    assert packet['bodyHtml'].count('cid:logo') == 1
    assert packet['inlineImages'][0]['name'] == 'marca.png'


def test_host_workspace_resolver_uses_authenticated_owner_not_request_path(tmp_path):
    appearance = Appearance(tmp_path,tmp_path / 'state',workspace_resolver=lambda owner:tmp_path / 'private' / owner)
    appearance.save('alice',{'fields':{'sender_name':'Alice'}})
    assert (tmp_path / 'private/alice/mail/profile.json').is_file()
    with pytest.raises(ValueError):
        appearance.save('alice',{'workspaceDirectory':str(tmp_path / 'private/bob')})
    assert not (tmp_path / 'private/bob/mail/profile.json').exists()


def test_graph_rich_reply_uses_body_and_prepared_recipients_without_comment():
    from cmail.graph import MicrosoftGraphProvider
    provider = object.__new__(MicrosoftGraphProvider)
    provider._call = Mock()
    provider.reply('message-id','Plain',body_html='<p>Resposta</p>',reply_recipients=['target@example.test'])
    packet = provider._call.call_args.args[2]
    assert 'comment' not in packet
    assert packet['message']['body'] == {'contentType':'HTML','content':'<p>Resposta</p>'}
    assert packet['message']['toRecipients'] == [{'emailAddress':{'address':'target@example.test'}}]


def test_legacy_content_type_meta_is_supported_without_allowing_refresh(tmp_path):
    appearance = Appearance(tmp_path,tmp_path / 'state')
    template = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head><body>{{body_html}}</body></html>'
    profile = {'templateHtml':template,'modes':{'new':{'template':'custom','signature':'none'}}}
    assert 'http-equiv="Content-Type"' in appearance.render('','Título','Texto',override=profile)['bodyHtml']
    with pytest.raises(ValueError):
        appearance.render('','Título','Texto',override={**profile,'templateHtml':template.replace('Content-Type','refresh')})
