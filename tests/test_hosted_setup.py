import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cmail.configuration import CmailConfiguration
from cmail.config import Config
from cmail.web import create_app, create_component_app


CALLBACK = 'http://localhost:2670/email/auth/google/callback'


def client_file(**changes):
    web = dict(client_id='synthetic.apps.googleusercontent.com', client_secret='synthetic-secret', redirect_uris=[CALLBACK])
    web.update(changes)
    return json.dumps({'web': web}).encode()


def fixture(tmp_path, **options):
    editor = CmailConfiguration(tmp_path/'config/cmail.config.json', root=tmp_path)
    editor.initialize()
    config = Config.from_file(editor.path, root=tmp_path)
    def resolver(request):
        return {'identifier':'fixture-owner','capabilities':[]} if request.headers.get('x-user') else None
    module = create_app(config, principal_resolver=resolver,
        setup_authorizer=lambda request: request.headers.get('x-user') == 'admin',
        setup_origin='http://localhost:2670', **options)
    host = FastAPI();host.mount('/email', module)
    return TestClient(host), editor, config


def payload(client):
    page = client.get('/email/setup', headers={'x-user':'admin','host':'untrusted.example'})
    assert page.status_code == 200
    assert CALLBACK in page.text and 'untrusted.example' not in page.text
    assert 'name="username"' not in page.text and 'name="clientSecret"' not in page.text
    return {key:re.search(f'name="{key}" value="([^"]+)"',page.text)[1] for key in ('csrf','revision')} | {'provider':'gmail'}


def test_admin_import_is_initial_only_and_keeps_oauth_pending(tmp_path):
    client, editor, config = fixture(tmp_path)
    values = payload(client)
    assert not config.state_dir.exists()
    response=client.post('/email/setup',data=values,files={'oauthClientFile':('client.json',client_file())},headers={'x-user':'admin'})
    assert response.status_code == 202
    assert 'synthetic-secret' not in response.text
    saved=Config.from_file(editor.path,root=tmp_path)
    assert saved.google_redirect_uri == CALLBACK
    assert saved.google_client_secret_file.read_text().strip() == 'synthetic-secret'
    assert saved.state_dir == config.state_dir
    assert not (config.state_dir/'cmail.sqlite3').exists()
    assert client.get('/email/health').json()['configured'] is False
    assert client.post('/email/setup',data=values,files={'oauthClientFile':('client.json',client_file())},headers={'x-user':'admin'}).status_code == 403


def test_setup_requires_admin_csrf_and_explicit_host_opt_in(tmp_path):
    client, editor, config = fixture(tmp_path)
    assert client.get('/email/setup',headers={'x-user':'ordinary'}).status_code == 403
    assert client.get('/email/setup').status_code == 401
    values=payload(client);values['csrf']='invalid'
    assert client.post('/email/setup',data=values,headers={'x-user':'admin'}).status_code == 403
    legacy=TestClient(create_app(config,principal_resolver=lambda r: {'identifier':'owner'}))
    assert legacy.get('/setup').status_code == 404
    assert not config.state_dir.exists()


@pytest.mark.parametrize('content',[
    b'{"installed":{}}',b'{"type":"authorized_user","refresh_token":"synthetic"}',
    b'not json',client_file(redirect_uris=['http://localhost:8020/auth/google/callback']),
    client_file(access_token='synthetic'),b'x'*65537],ids=['desktop','token','invalid-json','callback','access-token','oversized'])
def test_rejects_wrong_client_without_writing(tmp_path,content):
    client,editor,config=fixture(tmp_path)
    before=editor.path.read_bytes(); values=payload(client)
    result=client.post('/email/setup',data=values,files={'oauthClientFile':('client.json',content)},headers={'x-user':'admin'})
    assert result.status_code == 400
    assert editor.path.read_bytes() == before
    assert not config.state_dir.exists()


def test_stale_revision_and_component_factory_contract(tmp_path):
    client,editor,config=fixture(tmp_path)
    values=payload(client);values['revision']='a'*64
    assert client.post('/email/setup',data=values,files={'oauthClientFile':('client.json',client_file())},headers={'x-user':'admin'}).status_code == 409
    assert not config.state_dir.exists()
    module=create_component_app(tmp_path,{'configFile':editor.path,'principalResolver':lambda r: {'identifier':'owner'},
        'setupAuthorizer':lambda r:True,'setupOrigin':'http://localhost:2670'})
    assert TestClient(module).get('/setup').status_code == 200
    with pytest.raises(ValueError):
        create_app(config,principal_resolver=lambda r: {},setup_authorizer=lambda r: True,setup_origin='https://example.test/path')


def test_native_consent_after_host_applies_saved_configuration(tmp_path):
    from cmail.service import MailService
    client,editor,config=fixture(tmp_path)
    values=payload(client)
    assert client.post('/email/setup',data=values,files={'oauthClientFile':('client.json',client_file())},headers={'x-user':'admin'}).status_code == 202
    saved=Config.from_file(editor.path,root=tmp_path)
    service=MailService(saved)
    owners=[]
    def begin(owner):
        owners.append(owner)
        return 'https://accounts.google.com/o/oauth2/v2/auth?synthetic=1','synthetic-nonce'
    service.auth.begin=begin
    host=FastAPI();host.mount('/email',create_app(saved,service,principal_resolver=lambda r: {'identifier':'existing-owner'}))
    response=TestClient(host).get('/email/auth/google',follow_redirects=False)
    assert response.status_code == 302 and owners == ['existing-owner']
    assert 'Path=/email/auth/google/callback' in response.headers['set-cookie']


def test_oversized_form_is_rejected_before_multipart_parsing(tmp_path):
    client,editor,config=fixture(tmp_path)
    assert client.post('/email/setup',content=b'x'*98305,headers={'x-user':'admin'}).status_code == 413
    assert not config.state_dir.exists()


def test_hosted_upload_form_in_real_browser(tmp_path):
    import socket
    import threading
    import time
    import os
    from pathlib import Path
    import uvicorn
    from playwright.sync_api import sync_playwright
    client,editor,config=fixture(tmp_path)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(10)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(client.app,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:
            time.sleep(.02)
        assert server.started
        with sync_playwright() as runtime:
            executable=os.environ.get('CMAIL_TEST_BROWSER_EXECUTABLE')
            edge=Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
            if not executable and os.name == 'nt' and edge.is_file():
                executable=str(edge)
            browser=runtime.chromium.launch(headless=True,executable_path=executable)
            try:
                page=browser.new_page(extra_http_headers={'x-user':'admin'})
                page.goto(f'http://127.0.0.1:{port}/email/setup')
                page.locator('input[name="oauthClientFile"]').set_input_files({'name':'client.json','mimeType':'application/json','buffer':client_file()})
                page.get_by_role('button',name='Salvar esta conta').click()
                page.get_by_text('Configuração salva',exact=True).wait_for()
                assert 'Nenhuma caixa foi conectada ainda' in page.locator('body').inner_text()
                assert Config.from_file(editor.path,root=tmp_path).mode == 'gmail'
            finally:
                browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=5);listener.close()
