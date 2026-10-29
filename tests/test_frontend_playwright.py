import json
import socket
import threading
from pathlib import Path

import pytest
import uvicorn

from cmail.config import Config
from cmail.web import create_app
from cmail.service import MailService


def _server(app):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2048)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    return server, thread, port


def _demo_config(tmp_path: Path) -> Config:
    payload = {
        "schemaVersion": "1.0",
        "mode": "demo",
        "server": {
            "host": "127.0.0.1", "port": 8020, "openBrowser": False,
            "sessionHours": 12, "cookieSecure": False,
        },
        "state": {"directory": ".state"},
        "microsoft": {
            "clientId": "", "tenantId": "", "clientSecretFile": "", "redirectUri": "",
        },
        "imap": {
            "account": "", "username": "", "passwordFile": "", "imapHost": "",
            "imapPort": 993, "imapSecurity": "ssl", "smtpHost": "", "smtpPort": 587,
            "smtpSecurity": "starttls", "sentFolder": "Sent",
        },
    }
    (tmp_path / ".env").write_text("CMAIL_CONFIG_FILE=cmail.json\n", encoding="utf-8")
    (tmp_path / "cmail.json").write_text(json.dumps(payload), encoding="utf-8")
    return Config.load(tmp_path)


def _setup_config(tmp_path: Path) -> Config:
    selected = _demo_config(tmp_path)
    payload = json.loads(selected.config_file.read_text(encoding="utf-8"))
    payload["schemaVersion"] = "1.1"
    payload["mode"] = "setup"
    payload["microsoft"]["account"] = ""
    payload["google"] = {
        "account": "", "clientId": "", "clientSecretFile": "", "redirectUri": "",
    }
    selected.config_file.write_text(json.dumps(payload), encoding="utf-8")
    return Config.load(tmp_path)


def _assert_inside_viewport(page, selector: str) -> None:
    box = page.locator(selector).bounding_box()
    assert box is not None
    width = page.evaluate("window.innerWidth")
    assert box["x"] >= -0.5
    assert box["x"] + box["width"] <= width + 0.5


def test_demo_webmail_remains_accessible_at_supported_viewports(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    server, thread, port = _server(create_app(_demo_config(tmp_path)))
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
            except Exception as error:
                pytest.skip(f"Microsoft Edge indisponível para inspeção responsiva: {error}")
            try:
                page = browser.new_page()
                for width, height in ((1440, 900), (768, 1024), (390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")

                    badge = page.locator("#modeBadge")
                    assert badge.is_visible()
                    assert "Demonstração" in badge.inner_text()
                    assert "nenhum envio real" in badge.inner_text()
                    assert page.locator("#showListForm").is_visible()
                    assert page.locator("#newMessage").is_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

                    page.locator("#showListForm").click()
                    for selector in ("#modeBadge", "#showListForm", "#listForm", "#listName", "#listRecipients", "#saveList"):
                        assert page.locator(selector).is_visible()
                        _assert_inside_viewport(page, selector)
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    page.screenshot(path=str(tmp_path / f"cmail-{width}x{height}.png"), full_page=True)
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_single_account_setup_is_responsive_and_switches_provider_fields(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    server, thread, port = _server(create_app(_setup_config(tmp_path)))
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
            except Exception as error:
                pytest.skip(f"Microsoft Edge indisponível para inspeção responsiva: {error}")
            try:
                page = browser.new_page()
                for width, height in ((1440, 900), (768, 1024), (390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                    assert page.locator("h1").inner_text() == "Configurar CMAIL"
                    assert page.locator('input[value="outlook"]').is_checked()
                    assert page.locator('[data-provider-panel="oauth"]').is_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    page.locator('input[value="imap"]').check()
                    assert page.locator('[data-provider-panel="imap"]').is_visible()
                    assert page.locator('[data-provider-panel="oauth"]').is_hidden()
                    for selector in ('input[name="account"]', 'input[name="imapHost"]', 'input[name="smtpHost"]', '.setup-submit'):
                        assert page.locator(selector).is_visible()
                        _assert_inside_viewport(page, selector)
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


class ContextMailbox:
    """Synthetic messages; all mutations stay in memory and send is forbidden."""
    def __init__(self):
        self.items = [
            {"id": "one", "subject": "Proposta de integração", "from": {"name": "Marina Costa", "address": "marina@example.test"}, "to": [{"address": "equipe@example.test"}], "cc": [], "receivedAt": "2026-10-28T13:50:00-03:00", "isRead": False, "preview": "Olá! Seguem os próximos passos para nossa integração.", "body": "Olá, equipe!\n\nCompartilho os próximos passos para nossa integração.\nPodemos conversar na quinta-feira às 10h?\n\n1. Confirmar o escopo\n2. Revisar o cronograma\n3. Agendar a apresentação\n\nObrigada,\nMarina Costa", "attachments": [{"name": "Cronograma.pdf"}], "hasAttachments": True},
            {"id": "two", "subject": "Reunião de planejamento", "from": {"name": "Rafael Almeida", "address": "rafael@example.test"}, "receivedAt": "2026-10-28T12:30:00-03:00", "isRead": True, "preview": "Nosso encontro está confirmado para amanhã.", "body": "Encontro confirmado para amanhã."},
            {"id": "three", "subject": "Atualização do projeto", "from": {"name": "Equipe Produto", "address": "produto@example.test"}, "receivedAt": "2026-10-27T16:15:00-03:00", "isRead": False, "preview": "As novidades da semana já estão disponíveis.", "body": "As novidades da semana já estão disponíveis."},
        ]
        self.moves = []
        self.locations = {item["id"]: "INBOX" for item in self.items}
        self.deleted = []
    def folders(self):
        return [{"id": "INBOX", "name": "INBOX", "unread": 2}, {"id": "Archive", "name": "INBOX.Archive"}, {"id": "Sent", "name": "INBOX.Sent"}, {"id": "Drafts", "name": "INBOX.Drafts"}, {"id": "Junk", "name": "INBOX.Junk"}, {"id": "Trash", "name": "INBOX.Trash"}]
    def messages(self, folder, limit=50): return [item for item in self.items if self.locations[item["id"]] == folder]
    def message(self, folder, identifier): return next(item for item in self.items if item["id"] == identifier)
    def set_read(self, identifier, is_read):
        item = self.message("INBOX", identifier); item["isRead"] = is_read; return item
    def move(self, identifier, destination_id):
        self.moves.append((identifier, destination_id)); self.locations[identifier] = destination_id; return {"moved": True}
    def delete_permanently(self, identifier, *, folder):
        assert folder == "Trash" and self.locations[identifier] == "Trash"
        self.deleted.append(identifier); self.items = [item for item in self.items if item["id"] != identifier]
        return {"deletedPermanently": True}
    def reply(self, *args, **kwargs): raise AssertionError("No email in UI tests")
    def forward(self, *args, **kwargs): raise AssertionError("No email in UI tests")
    def send(self, *args, **kwargs): raise AssertionError("No email in UI tests")


def test_context_toolbar_selection_mutations_and_responsive_layout(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    mailbox = ContextMailbox()
    selected = _demo_config(tmp_path)
    server, thread, port = _server(create_app(selected, MailService(selected, mailbox)))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            assert page.locator("#messageActions").is_hidden()
            assert page.locator(".cm-folder").first.inner_text().startswith("Caixa de entrada")
            page.locator(".message-item").first.click()
            page.locator("#messageActions").wait_for(state="visible")
            assert page.get_by_role("button", name="Responder", exact=True).get_attribute("title") == "Responder"
            assert page.locator("#readAttachments").inner_text() == "Cronograma.pdf"
            for width, height in ((1440, 900), (1064, 700), (768, 1024), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                for selector in ("#reply", "#forward", "#toggleRead", "#moveMessage", "#trashMessage"):
                    _assert_inside_viewport(page, selector)
                page.screenshot(path=str(tmp_path / f"cmail-context-{width}.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.locator("#toggleRead").click()
            page.get_by_role("button", name="Marcar como não lida", exact=True).wait_for()
            assert mailbox.items[0]["isRead"]
            page.locator("#moveMessage").click()
            page.locator("#destinationFolder").select_option("Archive")
            page.locator("#confirmMove").click()
            page.locator("#moveDialog").wait_for(state="hidden")
            assert mailbox.moves == [("one", "Archive")]
            assert page.locator("#messageActions").is_hidden()
            page.locator("#messageFilter").fill("planejamento")
            assert page.locator(".message-item").count() == 1
            page.locator(".message-item").click()
            page.locator("#messageActions").wait_for(state="visible")
            page.locator("#trashMessage").click()
            page.locator("#messageActions").wait_for(state="hidden")
            assert mailbox.moves[-1] == ("two", "Trash")
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_context_toolbar_in_embedded_host_inherits_live_theme(tmp_path):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    selected = _demo_config(tmp_path)
    host = FastAPI()
    @host.get("/", response_class=HTMLResponse)
    def shell():
        return '<html style="--ca-ui-surface:#fff;--ca-ui-text:#20252b;--ca-ui-muted:#626b75;--ca-ui-action:#343d48;--ca-ui-border:#d5dae0;color-scheme:light"><body class="ca-shell" style="margin:0"><iframe title="Webmail" src="/cm/cmail/" style="width:100%;height:100vh;border:0"></iframe></body></html>'
    host.mount("/cm/cmail", create_app(selected, MailService(selected, ContextMailbox()), principal_resolver=lambda request: {"identifier": "synthetic-workspace", "capabilities": ["mail.read", "mail.manage", "mail.send", "lists.manage"]}))
    server, thread, port = _server(host)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1064, "height": 760})
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            frame = page.frame_locator('iframe[title="Webmail"]')
            frame.locator(".message-item").first.click()
            frame.locator("#messageActions").wait_for(state="visible")
            frame.locator("#reply").click()
            frame.locator("#body").fill("Rascunho preservado ao trocar de tema.")
            page.evaluate("""() => { const root=document.documentElement; for (const [key,value] of Object.entries({surface:'#161a25',text:'#e8ebf5',muted:'#9aa5ba',action:'#8b7cf8',border:'#30384b',canvas:'#0c0e14',danger:'#ed93a4'})) root.style.setProperty('--ca-ui-'+key,value); root.style.colorScheme='dark'; }""")
            from playwright.sync_api import expect
            expect(frame.locator("#readSubject")).to_have_css("color", "rgb(232, 235, 245)")
            assert frame.locator("#body").input_value() == "Rascunho preservado ao trocar de tema."
            frame.locator("#closeCompose").click()
            page.screenshot(path=str(tmp_path / "cmail-context-embedded-dark.png"), full_page=True)
            assert frame.locator("#messageActions").is_visible()
            assert frame.locator("body").evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_same_delete_button_trashes_then_permanently_deletes_synthetic_message(tmp_path):
    from playwright.sync_api import expect
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    mailbox = ContextMailbox()
    # Deletion-to-trash is distinct from the generic move toolbar capability.
    mailbox.message_actions = lambda: {"move": False, "trash": True, "deletePermanently": True}
    selected = _demo_config(tmp_path)
    server, thread, port = _server(create_app(selected, MailService(selected, mailbox)))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1064, "height": 760})
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.locator('.message-item[data-id="one"]').click()
            remove = page.get_by_role("button", name="Excluir", exact=True)
            expect(remove).to_be_visible()
            expect(remove).to_be_enabled()
            assert page.locator("#moveMessage").is_hidden()
            color = remove.evaluate("node => getComputedStyle(node).color")
            with page.expect_request(lambda request: request.url.endswith('/api/messages/one/trash')) as sent_to_trash:
                remove.click()
            assert sent_to_trash.value.post_data_json == {"folder": "INBOX"}
            expect(page.locator("#messageActions")).not_to_be_visible()
            expect(page.locator("#trashDialog")).not_to_be_visible()
            assert mailbox.locations["one"] == "Trash" and mailbox.deleted == []
            page.locator('.cm-folder[data-id="Trash"]').click()
            page.locator('.message-item[data-id="one"]').click()
            expect(remove).to_be_enabled()
            assert remove.evaluate("node => getComputedStyle(node).color") == color
            assert remove.get_attribute("title") == "Excluir definitivamente"
            remove.click()
            expect(page.locator("#trashTitle")).to_have_text("Excluir definitivamente?")
            expect(page.locator("#deleteExplanation")).to_contain_text("Não será possível recuperá-la")
            page.screenshot(path=str(tmp_path / "cmail-delete-permanently-confirm.png"), full_page=True)
            page.locator("#cancelTrash").click()
            assert mailbox.deleted == []
            remove.click()
            page.locator("#confirmTrash").click()
            expect(page.locator("#trashDialog")).not_to_be_visible()
            assert mailbox.deleted == ["one"]
            expect(page.locator("#messageActions")).not_to_be_visible()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
