"""Exercise actual modal, imports, sandboxed preview and prepared snapshot."""
import json

import pytest

from test_frontend_playwright import _server, _demo_config, _assert_inside_viewport
from test_inline_images import PNG
from cmail.web import create_app
from cmail.service import MailService


def test_modal_imports_independent_models_and_previews_prepared_snapshot(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    service = MailService(_demo_config(tmp_path))
    server, thread, port = _server(create_app(service.config,service))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge',headless=True)
            page = browser.new_page(viewport={'width':1440,'height':1000})
            errors = []
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/',wait_until='networkidle')
            page.get_by_role('button',name='Configurar template e assinatura',exact=True).click()
            expect(page.locator('#appearanceDialog')).to_be_visible()
            page.screenshot(path=str(tmp_path / 'appearance-settings.png'),full_page=True)
            page.locator('#appearance-sender_name').fill('Ana Exemplo')
            page.locator('#appearance-company_name').fill('Empresa de demonstração')
            page.locator('#appearance-new-template').select_option('custom')
            page.locator('#appearance-new-signature').select_option('custom')
            page.locator('summary').click()
            page.locator('#importTemplateHtml').set_input_files({'name':'email.html','mimeType':'text/html',
                'buffer':b'<div style="padding:16px">{{body_html}}{{signature_html}}</div>'})
            expect(page.locator('#appearanceTemplateHtml')).to_have_value('<div style="padding:16px">{{body_html}}{{signature_html}}</div>')
            page.locator('#appearanceSignatureHtml').fill('<strong>{{sender_name}}</strong><img src="cid:logo" alt="Logo de exemplo">')
            page.locator('#appearanceImages').set_input_files({'name':'logo.png','mimeType':'image/png','buffer':PNG})
            expect(page.locator('#appearanceAssets input')).to_have_value('logo')
            page.locator('#previewAppearance').click()
            preview = page.frame_locator('#appearancePreview')
            expect(preview.locator('strong')).to_have_text('Ana Exemplo')
            expect(preview.locator('img')).to_have_attribute('src', __import__('re').compile('data:image/png;base64,'))
            page.screenshot(path=str(tmp_path / 'appearance-desktop.png'),full_page=True)
            page.locator('#saveAppearance').click()
            expect(page.locator('#appearanceDialog')).not_to_be_visible()
            assert json.loads((service.appearance.user_root('') / 'profile.json').read_text(encoding='utf-8'))['fields']['sender_name'] == 'Ana Exemplo'
            page.locator('#newMessage').click()
            page.locator('#to').fill('test@example.test')
            page.locator('#subject').fill('Prévia de teste')
            page.locator('#body').fill('Conteúdo de teste, sem envio.')
            page.locator('#prepare').click()
            expect(page.locator('#confirm')).to_be_visible()
            expect(page.frame_locator('#sendPreview').locator('strong')).to_have_text('Ana Exemplo')
            assert 'test@example.test' in page.locator('#confirmText').inner_text()
            page.locator('#cancel').click()
            page.locator('#configureAppearance').click()
            page.locator('#resetAppearance').click()
            page.locator('#previewAppearance').click()
            expect(page.frame_locator('#appearancePreview').locator('h1')).to_have_text('Prévia da sua mensagem')
            page.set_viewport_size({'width':390,'height':844})
            for selector in ['#appearanceDialog','#saveAppearance','#previewAppearance']:
                _assert_inside_viewport(page,selector)
            page.screenshot(path=str(tmp_path / 'appearance-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
