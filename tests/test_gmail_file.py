"""Synthetic credentials only. No real network, consent, browser or delivery."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail import Config, Principal, create_api, render_email_template
from cmail.auth import AuthenticationError
from cmail.gmail import GMAIL_API, GOOGLE_TOKEN, GmailProvider
from cmail.gmail_file import GmailFileAuth, _NoRedirect, _request, main as gmail_main
from cmail.gmail_consent import GmailFileConsent
from cmail.api import create_component_api
from cmail.enviar import main as enviar_main
from cmail.service import MailService
from cmail.web import create_app


@pytest.fixture
def settings(tmp_path):
    value = json.loads((Path(__file__).parents[1] / 'config.example.json').read_text(encoding='utf-8'))
    value.update(schemaVersion='1.2', mode='gmail-file',
                 gmailFile={'account':'sender@example.com','tokenFile':'authorized.json'})
    value['server']['openBrowser'] = False
    path = tmp_path/'cmail.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return Config.from_file(path)


def credentials(settings, **changes):
    value = {'type':'authorized_user','token':'fake-access','refresh_token':'fake-refresh',
             'client_id':'fake-client','client_secret':'fake-secret','token_uri':GOOGLE_TOKEN,
             'expiry':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    value.update(changes)
    settings.gmail_token_file.write_text(json.dumps(value), encoding='utf-8')
    return settings.gmail_token_file.read_bytes()


def transport(calls, *, email='sender@example.com', refresh_status=200):
    def request(method,url,headers,body):
        calls.append((method,url,headers,body))
        if url == GOOGLE_TOKEN:
            return refresh_status, {'access_token':'new-fake','expires_in':3600}
        if url == GMAIL_API+'/profile':
            return 200, {'emailAddress':email}
        if url == GMAIL_API+'/messages/send':
            return 200, {'id':'fake-sent-id'}
        return 200, {'labels':[]}
    return request


def test_valid_token_checks_actual_account_and_never_writes(settings):
    original = credentials(settings)
    calls=[]
    auth=GmailFileAuth(settings,requester=transport(calls))
    assert auth.status()['account']=='sender@example.com'
    assert auth.access_token()=='fake-access'
    assert len(calls)==1 and calls[0][1]==GMAIL_API+'/profile'
    assert settings.gmail_token_file.read_bytes()==original


def test_expired_refreshes_once_in_memory_with_pinned_endpoint(settings):
    original=credentials(settings,expiry='2000-01-01T00:00:00Z',token_uri='https://accounts.google.com/o/oauth2/token')
    calls=[]
    auth=GmailFileAuth(settings,requester=transport(calls))
    assert auth.access_token()=='new-fake'
    assert auth.access_token()=='new-fake'
    assert [call[1] for call in calls]==[GOOGLE_TOKEN,GMAIL_API+'/profile']
    assert settings.gmail_token_file.read_bytes()==original


@pytest.mark.parametrize('change',[{'token_uri':'https://evil.example/token'},
    {'token_uri':{}},{'type':'service_account'},{'refresh_token':''}, {'expiry':'nonsense'},
    {'token':'bad\nheader'}])
def test_invalid_credentials_fail_before_network(settings,change):
    credentials(settings,**change)
    request=Mock()
    with pytest.raises(AuthenticationError): GmailFileAuth(settings,requester=request).access_token()
    request.assert_not_called()


@pytest.mark.parametrize('content',[None,b'{bad json',b'[]',b'\xff',b'x'*65537],
                         ids=['missing','json','array','encoding','oversized'])
def test_missing_and_invalid_file_are_sanitized(settings,content):
    if content is not None: settings.gmail_token_file.write_bytes(content)
    with pytest.raises(AuthenticationError) as error: GmailFileAuth(settings).access_token()
    assert 'authorized.json' not in str(error.value)


def test_refresh_rejected_or_account_mismatch_never_sends(settings):
    credentials(settings,expiry='2000-01-01T00:00:00Z')
    for options in ({'refresh_status':400},{'email':'other@example.com'}):
        calls=[]
        with pytest.raises(AuthenticationError):
            GmailFileAuth(settings,requester=transport(calls,**options)).status()
        assert not any('/messages/send' in c[1] for c in calls)


def test_file_change_invalidates_cached_identity(settings):
    credentials(settings)
    calls=[]
    request=Mock(side_effect=[(200,{'emailAddress':'sender@example.com'}),
                             (200,{'emailAddress':'other@example.com'})])
    auth=GmailFileAuth(settings,requester=request)
    auth.access_token()
    credentials(settings,token='replaced-fake')
    with pytest.raises(AuthenticationError): auth.access_token()


def test_new_route_cannot_impersonate_owner_or_mount_as_web(settings):
    service=MailService(settings,mail_provider=Mock())
    payload={'recipients':['target@example.com'],'subject':'Ação','body':'Olá'}
    forged=Principal('web-id','other@example.com',frozenset({'mail.send'}),'owner')
    with pytest.raises(PermissionError): service.prepare(payload,forged)
    with pytest.raises(PermissionError): service.principal_for_owner('owner')
    with pytest.raises(PermissionError): service.connection_status('owner')
    with pytest.raises(ValueError): create_app(settings)
    with pytest.raises(ValueError): create_component_api(settings.root,{'configFile':settings.config_file})


def test_config_account_change_cannot_claim_previous_draft(settings):
    first=MailService(settings,mail_provider=Mock())
    draft=first.prepare({'recipients':['target@example.com'],'subject':'Ação','body':'Olá'})
    assert draft['sender']=='sender@example.com'
    second=MailService(replace(settings,gmail_file_account='other@example.com'),mail_provider=Mock())
    with pytest.raises(ValueError): second.execute(draft['draftId'],draft['confirmationToken'])


def test_public_api_uses_file_route_without_web_identity(settings,monkeypatch):
    credentials(settings)
    calls=[]
    monkeypatch.setattr('cmail.gmail_file._request',transport(calls))
    api=create_api(settings)
    principal=Principal.local_operator()
    draft=api.prepare_send(principal,{'recipients':['target@example.com'],'subject':'Ação',
                                     'body':'Olá','bodyHtml':'<p>Olá</p>'})
    assert calls==[]
    result=api.execute_send(principal,draft['draftId'],draft['confirmationToken'])
    assert result['id']=='fake-sent-id'
    with pytest.raises(ValueError): api.execute_send(principal,draft['draftId'],draft['confirmationToken'])
    assert len([c for c in calls if c[1].endswith('/messages/send')])==1


def test_uncertain_send_is_not_replayed(settings):
    provider=Mock()
    provider.send.side_effect=AuthenticationError('Falha sanitizada.')
    service=MailService(settings,mail_provider=provider)
    draft=service.prepare({'recipients':['target@example.com'],'subject':'Ação','body':'Olá'})
    with pytest.raises(AuthenticationError): service.execute(draft['draftId'],draft['confirmationToken'])
    with pytest.raises(ValueError): service.execute(draft['draftId'],draft['confirmationToken'])
    assert provider.send.call_count==1


def test_redirect_and_arbitrary_endpoint_fail_without_network():
    with pytest.raises(AuthenticationError): _request('POST','http://127.0.0.1/token',{},b'')
    with pytest.raises(AuthenticationError): _NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example')


def test_sanitizes_low_level_errors(settings):
    credentials(settings)
    auth=GmailFileAuth(settings,requester=Mock(side_effect=RuntimeError('fake-secret /private/path')))
    with pytest.raises(AuthenticationError) as error: auth.status()
    assert 'fake-secret' not in str(error.value) and '/private' not in str(error.value)


def test_consent_has_pkce_exact_state_account_and_no_browser(settings,tmp_path,monkeypatch):
    client=tmp_path/'client.json'
    client.write_text(json.dumps({'installed':{'client_id':'fake','client_secret':'fake',
                                               'token_uri':GOOGLE_TOKEN}}))
    output=tmp_path/'new-token.json'
    requests=[]
    def request(method,url,headers,body):
        requests.append((method,url,headers,body))
        if method=='POST': return 200, {'access_token':'fake','refresh_token':'fake-refresh','expires_in':3600}
        return 200, {'emailAddress':'sender@example.com'}
    flow=GmailFileConsent(client,output,'sender@example.com',
                         'http://127.0.0.1:54321/auth/callback',requester=request)
    url=flow.authorization_url()
    query=parse_qs(urlsplit(url).query)
    assert query['code_challenge_method']==['S256']
    assert 'fake-secret' not in url
    with pytest.raises(AuthenticationError): flow.complete(flow.redirect_uri+'?state=wrong&code=fake')
    assert requests==[] and not output.exists()
    callback=flow.redirect_uri+'?state='+query['state'][0]+'&code=fake'
    assert flow.complete(callback)['authorized']
    assert json.loads(output.read_text())['type']=='authorized_user'
    assert 'code_verifier=' in requests[0][3].decode()
    with pytest.raises(AuthenticationError): flow.complete(callback)


def test_cli_status_refresh_do_not_open_browser(settings,monkeypatch,capsys):
    credentials(settings)
    monkeypatch.setattr('cmail.gmail_file._request',transport([]))
    browser=Mock(side_effect=AssertionError('browser forbidden'))
    monkeypatch.setattr('webbrowser.open',browser)
    for action in ['status','refresh']:
        assert gmail_main([action,'--config-file',str(settings.config_file)])==0
        assert json.loads(capsys.readouterr().out)['ok']
    browser.assert_not_called()


def test_template_escape_missing_fields_unicode_and_limit(tmp_path):
    template=tmp_path/'template.html'
    template.write_text('<h1>{{title}}</h1><div>{{content}}</div>',encoding='utf-8')
    value=render_email_template(template,body='Ação & atenção',fields={'title':'Olá <x>'},html_fields={'content':'<b>ação</b>'})
    assert value=={'body':'Ação & atenção','bodyHtml':'<h1>Olá &lt;x&gt;</h1><div><b>ação</b></div>'}
    with pytest.raises(ValueError): render_email_template(template,body='Olá',fields={'title':'a'})
    with pytest.raises(ValueError): render_email_template(template,body='Olá',fields={'title':'a'},html_fields={'title':'b'})
    with pytest.raises(ValueError): render_email_template(template,body='Olá',fields={'title':'a','content':'x'*200000})
    template.write_text('{{user.secret}}')
    with pytest.raises(ValueError): render_email_template(template,body='Olá')


def test_cli_preview_then_execute_never_rerenders(settings,tmp_path,monkeypatch,capsys):
    credentials(settings)
    calls=[]
    monkeypatch.setattr('cmail.gmail_file._request',transport(calls))
    template=tmp_path/'mail.html'; template.write_text('<p>{{name}}</p>',encoding='utf-8')
    base=['--gmail','--config-file',str(settings.config_file)]
    assert enviar_main(base+['--to','target@example.com','--subject','Ação','--body','Olá',
                            '--template',str(template),'--set','name=Fictício'])==0
    draft=json.loads(capsys.readouterr().out)['result']
    assert calls==[]
    template.write_text('CHANGED')
    assert enviar_main(base+['--execute','--draft-id',draft['draftId'],
                            '--confirmation-token',draft['confirmationToken']])==0
    result=json.loads(capsys.readouterr().out)
    assert result['ok']
    assert len([c for c in calls if c[1].endswith('/messages/send')])==1
    import base64
    sent=json.loads(next(c[3] for c in calls if c[1].endswith('/messages/send')))
    mime=base64.urlsafe_b64decode(sent['raw']+'='*(-len(sent['raw'])%4))
    from email import message_from_bytes
    from email.policy import default
    message=message_from_bytes(mime,policy=default)
    assert message.get_body(preferencelist=('html',)).get_content().strip()=='<p>Fictício</p>'
    assert enviar_main(base+['--execute','--to','target@example.com'])==1


@pytest.mark.parametrize('mutate',[
    lambda v:v['gmailFile'].update(extra='unknown'),
    lambda v:v['gmailFile'].update(account='not-an-address'),
    lambda v:v['server'].update(openBrowser=True),
    lambda v:v.update(schemaVersion='1.1'),
])
def test_new_schema_is_explicit_and_closed(settings,mutate):
    value=json.loads(settings.config_file.read_text())
    mutate(value)
    settings.config_file.write_text(json.dumps(value))
    with pytest.raises(ValueError): Config.from_file(settings.config_file)


@pytest.mark.parametrize('failure',['wrong-account','exchange-failed','expired','denied','duplicate-code'])
def test_consent_failure_never_writes_token(settings,tmp_path,failure):
    client=tmp_path/'client.json'
    client.write_text(json.dumps({'installed':{'client_id':'fake','client_secret':'fake'}}))
    output=tmp_path/'consent-token.json'
    def request(method,url,headers,body):
        if method=='POST':
            return (400 if failure=='exchange-failed' else 200),{
                'access_token':'fake','refresh_token':'fake','expires_in':3600}
        return 200,{'emailAddress':'other@example.com' if failure=='wrong-account' else 'sender@example.com'}
    flow=GmailFileConsent(client,output,'sender@example.com',
                         'http://127.0.0.1:54321/auth/callback',requester=request)
    state=parse_qs(urlsplit(flow.authorization_url()).query)['state'][0]
    if failure=='expired': flow._started-=601
    callback=flow.redirect_uri+'?state='+state+'&code=fake'
    if failure=='denied': callback+='&error=access_denied'
    if failure=='duplicate-code': callback+='&code=second'
    with pytest.raises(AuthenticationError): flow.complete(callback)
    assert not output.exists()


def test_cli_files_escape_and_refuse_new_payload_on_execute(settings,tmp_path,monkeypatch,capsys):
    credentials(settings)
    request=Mock(side_effect=AssertionError('no provider during preview'))
    monkeypatch.setattr('cmail.gmail_file._request',request)
    template=tmp_path/'t.html';template.write_text('<h1>{{title}}</h1>{{content}}',encoding='utf-8')
    plain=tmp_path/'plain.txt';plain.write_text('Olá, atenção.',encoding='utf-8')
    title=tmp_path/'title.txt';title.write_text('Ação & <script>',encoding='utf-8')
    fragment=tmp_path/'fragment.html';fragment.write_text('<p>Apresentação</p>',encoding='utf-8')
    base=['--gmail','--config-file',str(settings.config_file)]
    assert enviar_main(base+['--to','target@example.com','--subject','Ação',
        '--body-file',str(plain),'--template',str(template),'--set-file','title='+str(title),
        '--html-field-file','content='+str(fragment)])==0
    preview=json.loads(capsys.readouterr().out)['result']
    assert 'Ação &amp; &lt;script&gt;' in json.dumps(preview,ensure_ascii=False)
    assert enviar_main(base+['--execute','--draft-id',preview['draftId'],
        '--confirmation-token',preview['confirmationToken'],'--body','alterado'])==1
    request.assert_not_called()
