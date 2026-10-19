"""Thin two-phase local Gmail-file email CLI. No transport duplication."""
import argparse
import json
from pathlib import Path

from .api import create_api
from .config import Config
from .service import Principal
from .template_render import render_email_template, LIMIT


def _text_file(filename):
    try:
        with Path(filename).open("rb") as stream:
            raw = stream.read(LIMIT * 4 + 4)
        text = raw.decode("utf-8-sig")
        if len(raw) > LIMIT * 4 or len(text) > LIMIT:
            raise ValueError()
        return text
    except (OSError, UnicodeError, ValueError):
        raise ValueError("Arquivo de texto UTF-8 ausente ou inválido.") from None


def _fields(direct, filenames):
    result = {}
    for value, is_file in [(v, False) for v in direct] + [(v, True) for v in filenames]:
        key, separator, content = value.partition("=")
        if not separator or not key or key in result:
            raise ValueError("Campo de template inválido ou duplicado.")
        result[key] = _text_file(content) if is_file else content
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare um e-mail; execute somente o rascunho confirmado.")
    parser.add_argument("--gmail", action="store_true", required=True,
                        help="Seleciona exclusivamente o modo local gmail-file.")
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--to", action="append", default=[])
    parser.add_argument("--subject")
    body = parser.add_mutually_exclusive_group()
    body.add_argument("--body")
    body.add_argument("--body-file")
    html = parser.add_mutually_exclusive_group()
    html.add_argument("--html-file")
    html.add_argument("--template")
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--set-file", action="append", default=[])
    parser.add_argument("--html-field", action="append", default=[])
    parser.add_argument("--html-field-file", action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--draft-id")
    parser.add_argument("--confirmation-token")
    args = parser.parse_args(argv)
    try:
        config = Config.from_file(args.config_file)
        if config.mode != "gmail-file":
            raise ValueError("--gmail exige configuração gmail-file, não OAuth web.")
        rendering = any((args.to, args.subject is not None, args.body is not None,
            args.body_file, args.html_file, args.template, args.set, args.set_file,
            args.html_field, args.html_field_file))
        if args.execute:
            if rendering or not args.draft_id or not args.confirmation_token:
                raise ValueError("Execute somente draft-id e confirmation-token, sem novo conteúdo.")
            api = create_api(config)
            result = api.execute_send(Principal.local_operator(), args.draft_id, args.confirmation_token)
        else:
            if args.draft_id or args.confirmation_token or not args.to or not args.subject:
                raise ValueError("Preparação exige destinatários e assunto, sem IDs de execução.")
            if any((args.set, args.set_file, args.html_field, args.html_field_file)) and not args.template:
                raise ValueError("Campos exigem --template.")
            text = _text_file(args.body_file) if args.body_file else args.body
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Alternativa texto é obrigatória.")
            payload = {"recipients": args.to, "subject": args.subject, "body": text}
            if args.template:
                payload.update(render_email_template(args.template, body=text,
                    fields=_fields(args.set, args.set_file),
                    html_fields=_fields(args.html_field, args.html_field_file)))
            elif args.html_file:
                payload["bodyHtml"] = _text_file(args.html_file)
            elif any((args.set, args.set_file, args.html_field, args.html_field_file)):
                raise ValueError("Campos exigem --template.")
            api = create_api(config)
            result = api.prepare_send(Principal.local_operator(), payload)
        print(json.dumps({"ok": True, "phase": "execute" if args.execute else "preview",
                          "result": result}, ensure_ascii=False))
        return 0
    except Exception:
        # No traceback/provider body/path/token in the facade output.
        print(json.dumps({"ok": False, "error": "email_operation_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
