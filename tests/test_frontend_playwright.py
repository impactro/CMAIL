import json
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from cmail.config import Config
from cmail.web import create_app


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
    server = make_server("127.0.0.1", 0, create_app(_demo_config(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
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
                    page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle")

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
        server.shutdown()
        thread.join(timeout=5)


def test_single_account_setup_is_responsive_and_switches_provider_fields(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    server = make_server("127.0.0.1", 0, create_app(_setup_config(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
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
                    page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle")
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
        server.shutdown()
        thread.join(timeout=5)
