"""Strict local HTML placeholders; no template code or provider execution."""
import html
import re
from pathlib import Path
from typing import Mapping

LIMIT = 200000
PLACEHOLDER = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


def render_template_text(template: str, *, fields: Mapping[str, str] | None = None,
                         html_fields: Mapping[str, str] | None = None) -> str:
    """Render trusted source with escaped text and explicit HTML slots, without I/O."""
    if not isinstance(template, str) or len(template) > LIMIT:
        raise ValueError("Template inválido ou acima do limite.")
    regular, trusted = dict(fields or {}), dict(html_fields or {})
    if regular.keys() & trusted.keys():
        raise ValueError("Campo duplicado entre texto e HTML.")
    values = {}
    for name, value in {**regular, **trusted}.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("Nome de campo inválido.")
        if not isinstance(value, str) or len(value) > LIMIT:
            raise ValueError("Valor de campo inválido.")
        values[name] = value if name in trusted else html.escape(value, quote=True)
    # No expressions, include, attribute access, formatters or executable blocks.
    residue = PLACEHOLDER.sub("", template)
    if any(marker in residue for marker in ("{{", "}}", "{%", "{#")):
        raise ValueError("Template aceita somente placeholders {{nome}}.")
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise ValueError("Campo obrigatório do template não fornecido.")
        return values[key]
    rendered = PLACEHOLDER.sub(replace, template)
    if not rendered.strip() or len(rendered) > LIMIT:
        raise ValueError("HTML final vazio ou maior que 200 mil caracteres.")
    return rendered


def render_email_template(template_path, *, body: str,
                          fields: Mapping[str, str] | None = None,
                          html_fields: Mapping[str, str] | None = None) -> dict[str, str]:
    if not isinstance(body, str) or not body.strip() or len(body) > LIMIT:
        raise ValueError("Alternativa texto é obrigatória e limitada a 200 mil caracteres.")
    try:
        with Path(template_path).open("rb") as stream:
            raw = stream.read(LIMIT * 4 + 4)
        template = raw.decode("utf-8-sig")
        if len(raw) > LIMIT * 4 or len(template) > LIMIT:
            raise ValueError()
    except (OSError, UnicodeError, ValueError):
        raise ValueError("Template UTF-8 ausente, inválido ou muito grande.") from None
    return {"body": body, "bodyHtml": render_template_text(template, fields=fields, html_fields=html_fields)}
