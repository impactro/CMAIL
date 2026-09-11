"""CLI e processo autoexecutável do CMAIL."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from pathlib import Path

from waitress import serve

from .config import Config
from .service import MailService
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


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.load()
    service = MailService(config)
    if args.action == "check-config": result = {"ok": True, "config": config.public()}
    elif args.action == "status": result = {"ok": True, **service.status(args.live)}
    elif args.action == "list-folders": result = {"ok": True, "folders": service.provider.folders()}
    elif args.action == "list-messages": result = {"ok": True, "messages": service.provider.messages(args.folder, args.limit)}
    elif args.action == "lists":
        result = {"ok": True, "lists": service.store.lists()}
        if args.input_json:
            payload = _json_file(args.input_json)
            result["saved"] = service.store.save_list(str(payload.get("name") or ""), payload.get("recipients") or [])
    elif args.action == "send-prepare": result = {"ok": True, "preview": service.prepare(_json_file(args.input_json))}
    elif args.action == "send-execute":
        if not args.execute: raise ValueError("send-execute exige --execute.")
        result = {"ok": True, "result": service.execute(args.draft_id, args.confirmation_token)}
    else:
        url = f"http://{config.host}:{config.port}/"
        if config.open_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        serve(create_app(config, service), host=config.host, port=config.port, threads=4)
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
