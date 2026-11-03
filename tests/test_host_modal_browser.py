"""Real CMAIL with an explicit, synthetic CA/CWH presentation host."""
import os
from pathlib import Path
import pytest
from test_frontend_playwright import _server,_demo_config
from cmail.web import create_app
from cmail.service import MailService

@pytest.mark.parametrize('host,width',[('ca',1440),('ca',390),('cwh',1440),('cwh',390)])
def test_host_modal_slots_theme_and_central_errors(tmp_path,host,width):
    assets=os.environ.get('CA_MODAL_ASSET_ROOT')
    if not assets:pytest.skip('Explicit CA_MODAL_ASSET_ROOT is required for cross-product integration')
    assets=Path(assets)
    from playwright.sync_api import sync_playwright,expect
    service=MailService(_demo_config(tmp_path));server,thread,port=_server(create_app(service.config,service))
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':width,'height':720})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                name=r.request.url.split('/')[-1].split('?')[0]
                if name in {'ca-modal.js','ca-modal.css','app-feedback.js','app-feedback.css'}:
                    r.fulfill(body=(assets/name).read_bytes(),content_type='text/css' if name.endswith('.css') else 'application/javascript')
                elif name=='fixture-host':
                    r.fulfill(content_type='text/html',body=f'<html data-ca-theme-provider="{host}" style="--ca-ui-text:#fff;--ca-ui-surface:#192632;--ca-ui-border:#76828b;--ca-ui-action:#337a68;--ca-modal-header-bg:#225533"><head><script src="/ca-modal.js"></script><script src="/app-feedback.js"></script></head><body style="margin:0"><header data-ca-feedback-header><strong>Host</strong></header><iframe id="embedded-area-frame" data-ca-host-component="cmail" src="/template" style="width:100%;height:650px;border:0"></iframe></body></html>')
                else:r.continue_()
            page.route('**/*',route);page.goto(f'http://127.0.0.1:{port}/fixture-host')
            page.evaluate('window.events=[];CAAppMessages.configure({diagnostics:async e=>{events.push(e);return {reference:"fixture-log"}}})')
            view=page.frame_locator('#embedded-area-frame');dialog=view.locator('#appearanceDialog')
            expect(dialog).to_be_visible();expect(dialog).to_have_attribute('data-modal-provider','host')
            expect(dialog.locator('header')).to_have_css('background-color','rgb(34, 85, 51)')
            head=dialog.locator('header').bounding_box();foot=dialog.locator('footer').bounding_box()
            view.locator('details summary').click();body=dialog.locator('.cm-modal-content');body.evaluate('(e)=>e.scrollTop=e.scrollHeight')
            assert abs(dialog.locator('header').bounding_box()['y']-head['y'])<2
            assert abs(dialog.locator('footer').bounding_box()['y']-foot['y'])<2
            page.evaluate('document.documentElement.style.setProperty("--ca-modal-header-bg","#365577")')
            expect(dialog.locator('header')).to_have_css('background-color','rgb(54, 85, 119)')
            view.locator('#appearanceExtraFields').fill('not-json')
            view.locator('#previewAppearance').click()
            expect(page.locator('header .ca-miniapp-feedback')).to_be_visible()
            expect(view.locator('#appearanceError')).to_have_text('')
            page.wait_for_function('events.length===1')
            assert page.evaluate('events[0].data.component')=='cmail'
            assert page.evaluate('events[0].data.operation')=='appearance'
            page.screenshot(path=str(tmp_path/f'{host}-{width}.png'))
            page.get_by_role('button',name='Fechar mensagem').click()
            view.locator('#closeAppearance').click();expect(dialog).not_to_be_visible()
            assert not errors,errors
            browser.close()
    finally:server.should_exit=True;thread.join(timeout=5)
