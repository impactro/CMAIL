"""CLI e processo autoexecutável do CMAIL."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from pathlib import Path
from typing import Callable

from waitress import create_server

from .config import Config
from .service import MailService, Principal
from .web import create_app


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="cmail")
    actions = value.add_subparsers(dest="action", required=True)
    actions.add_parser("check-config")
    status = actions.add_parser("status"); status.add_argument("--live", action="store_true")
    folders = actions.add_parser("list-folders")
    messages = actions.add_parser("list-messages"); messages.add_argument("--folder", default="INBOX"); messages.add_argument("--limit", type=int, default=50)
    lists = actions.add_parser("lists"); lists.add_argument("--input-json")
    prepare = actions.add_parser("send-prepare"); prepare.add_argument("--input-json", required=True)
    execute = actions.add_parser("send-execute"); execute.add_argument("--draft-id", required=True); execute.add_argument("--confirmation-token", required=True); execute.add_argument("--execute", action="store_true")
    actions.add_parser("serve")
    return value


def _json_file(path: str) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("JSON deve ser um objeto.")
    return value


def _serve(
    initial_config: Config,
    *,
    config_loader: Callable[[], Config] = Config.load,
    service_factory: Callable[[Config], MailService] = MailService,
    app_factory: Callable = create_app,
    server_factory: Callable = create_server,
    timer_factory: Callable = threading.Timer,
) -> int:
    """Executa o servidor e recarrega o JSON após uma configuração salva."""
    config = initial_config
    browser_opened = False
    while True:
        service = service_factory(config)
        restart_requested = threading.Event()
        server_holder: dict[str, object] = {}

        def schedule_restart() -> None:
            if restart_requested.is_set():
                return
            restart_requested.set()

            def stop_listener() -> None:
                server_holder["server"].close()  # type: ignore[attr-defined]

            timer = timer_factory(1.0, stop_listener)
            timer.daemon = True
            timer.start()

        app = app_factory(config, service, restart_callback=schedule_restart)
        server = server_factory(app, host=config.host, port=config.port, threads=4)
        server_holder["server"] = server
        if config.open_browser and not browser_opened:
            url = f"http://{config.host}:{config.port}/"
            timer = timer_factory(0.8, lambda: webbrowser.open(url))
            timer.daemon = True
            timer.start()
            browser_opened = True
        server.run()
        dispatcher = getattr(server, "task_dispatcher", None)
        if dispatcher is not None:
            dispatcher.shutdown()
        if not restart_requested.is_set():
            return 0
        config = config_loader()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load()
    if args.action == "serve":
        return _serve(config)
    service = MailService(config)
    local = service.config.mode not in {"microsoft", "gmail"}
    if not local and args.action not in {"check-config", "status", "serve"}:
        raise ValueError("No modo Microsoft, use o login web ou a API Python com Principal autenticado.")
    if args.action == "check-config": result = {"ok": True, "config": config.public()}
    elif args.action == "status": result = {"ok": True, **service.status(args.live)}
    elif args.action == "list-folders": result = {"ok": True, "folders": service.folders(Principal.local_operator())}
    elif args.action == "list-messages": result = {"ok": True, "messages": service.messages(Principal.local_operator(), args.folder, args.limit)}
    elif args.action == "lists":
        result = {"ok": True, "lists": service.lists(Principal.local_operator())}
        if args.input_json:
            payload = _json_file(args.input_json)
            result["saved"] = service.save_list(Principal.local_operator(), str(payload.get("name") or ""), payload.get("recipients") or [])
    elif args.action == "send-prepare": result = {"ok": True, "preview": service.prepare(_json_file(args.input_json))}
    elif args.action == "send-execute":
        if not args.execute: raise ValueError("send-execute exige --execute.")
        result = {"ok": True, "result": service.execute(args.draft_id, args.confirmation_token)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
