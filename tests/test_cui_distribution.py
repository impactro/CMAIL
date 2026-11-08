"""Packaged frontend contracts, independent of live mailbox credentials."""
import hashlib
import json
import os
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Environment
from cmail.cui_assets import CuiStaticFiles, template_environment


def test_aliases_keep_private_templates_out_of_public_vendor():
    root = Path(__file__).resolve().parents[1] / 'cmail'
    manifest = json.loads((root/'static/vendor/cui/cui.asset.json').read_text(encoding='utf8'))
    app = FastAPI()
    app.mount('/static', CuiStaticFiles(package=root, static='static'))
    with TestClient(app) as client:
        assert client.get('/static/style.css').status_code == 200
        base = '/static/vendor/cui/' + manifest['release'] + '/'
        response = client.get(base + 'cui-host.js')
        assert response.status_code == 200 and 'immutable' in response.headers['cache-control']
        assert client.get(base + 'hosts/cmail/templates/index.html').status_code == 404
        assert client.post('/static/style.css').status_code == 405
        for alias, name in manifest['resources'].items():
            if alias.startswith('static/'):
                response = client.get('/static/' + alias.removeprefix('static/'))
                assert response.status_code == 200, alias
                assert hashlib.sha256(response.content).hexdigest() == manifest['files'][name]['sha256']


@pytest.mark.parametrize('method', ['get', 'head'])
@pytest.mark.parametrize('variant', ['canonical', 'prefix', 'extension', 'all'])
def test_packaged_templates_are_private_in_named_mounts(method, variant):
    root = Path(__file__).resolve().parents[1] / 'cmail'
    manifest = json.loads((root/'static/vendor/cui/cui.asset.json').read_text(encoding='utf8'))
    app = FastAPI()
    app.mount('/named/static', CuiStaticFiles(package=root, static='static'))
    with TestClient(app) as client:
        for alias, name in manifest['resources'].items():
            if not alias.startswith('templates/'):
                continue
            path = 'vendor/cui/' + manifest['release'] + '/' + name
            if variant == 'prefix':
                path = path.replace('vendor/cui/', 'vendor/CUI/')
            elif variant == 'extension':
                path = path.removesuffix('.html') + '.HTML'
            elif variant == 'all':
                path = path.upper()
            assert getattr(client, method)('/named/static/' + path).status_code == 404, path


def test_cached_template_reloads_when_previous_snapshot_is_retired(tmp_path):
    vendor = tmp_path/'static/vendor/cui'
    vendor.mkdir(parents=True)
    first = vendor/'one/template.html'
    first.parent.mkdir()
    first.write_text('<p>{{ value }}</p>', encoding='utf8')
    def receipt(release):
        path = vendor/'cui.asset.json'
        previous = path.stat().st_mtime_ns if path.exists() else None
        path.write_text(json.dumps({'package':'@crania/ui','contract':'cui.ui.v1',
            'release':release,'files':{'template.html':{}},'resources':{'templates/index.html':'template.html'}}), encoding='utf8')
        if previous is not None:
            # Simulate an observable publication; immediate Windows writes can share an mtime.
            stamp = max(path.stat().st_mtime_ns, previous + 1_000_000_000)
            os.utime(path, ns=(stamp, stamp))
    receipt('one')
    env = Environment(loader=template_environment(tmp_path), autoescape=True)
    assert env.get_template('index.html').render(value='<script>') == '<p>&lt;script&gt;</p>'
    second = vendor/'two/template.html'
    second.parent.mkdir()
    second.write_text('<strong>{{ value }}</strong>', encoding='utf8')
    first.unlink()
    receipt('two')
    assert env.get_template('index.html').render(value='new') == '<strong>new</strong>'


def test_only_public_fingerprinted_assets_are_cached_in_the_real_mail_app(tmp_path):
    from cmail.web import create_app
    from helpers import config
    root = Path(__file__).resolve().parents[1] / 'cmail'
    manifest = json.loads((root/'static/vendor/cui/cui.asset.json').read_text(encoding='utf8'))
    with TestClient(create_app(config(tmp_path))) as client:
        response = client.get('/static/vendor/cui/' + manifest['release'] + '/cui-host.js')
        assert response.status_code == 200 and 'immutable' in response.headers['cache-control']
        for path in ('/', '/api/status', '/static/cm-theme.css'):
            assert client.get(path).headers['cache-control'] == 'no-store'


def test_legacy_module_alias_keeps_relative_imports_under_a_named_mount(tmp_path):
    vendor = tmp_path/'static/vendor/cui'
    module = vendor/'one/hosts/sample/feature.mjs'
    module.parent.mkdir(parents=True)
    module.write_text("import './dependency.mjs';", encoding='utf8')
    module.with_name('dependency.mjs').write_text('export const ready=true;', encoding='utf8')
    (vendor/'cui.asset.json').write_text(json.dumps({'package':'@crania/ui','contract':'cui.ui.v1',
        'release':'one','files':{'hosts/sample/feature.mjs':{'canonicalUrl':True}},
        'resources':{'static/feature.mjs':'hosts/sample/feature.mjs'}}),encoding='utf8')
    app=FastAPI()
    app.mount('/named/static',CuiStaticFiles(package=tmp_path,static='static'))
    with TestClient(app) as client:
        response=client.get('/named/static/feature.mjs',follow_redirects=False)
        assert response.status_code==307
        location=response.headers['location']
        assert location=='/named/static/vendor/cui/one/hosts/sample/feature.mjs'
        assert client.get(location).status_code==200
        assert client.get(location.replace('feature.mjs','dependency.mjs')).status_code==200
