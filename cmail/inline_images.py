"""Bounded inline raster images. No paths, downloads, credentials or sends."""
import base64
import binascii
import hashlib
import re
from html.parser import HTMLParser

MAX_COUNT = 8
MAX_BYTES = 2 * 1024 * 1024
CID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}(?:@[A-Za-z0-9][A-Za-z0-9.-]{0,63})?')
TYPES = {'image/png': '.png', 'image/jpeg': '.jpg'}


class _References(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            value = (dict(attrs).get('src') or '').strip()
            if value.lower().startswith('cid:'):
                identifier = value[4:]
                if not CID.fullmatch(identifier):
                    raise ValueError('Referência CID inválida.')
                self.ids.add(identifier)

    handle_startendtag = handle_starttag


def normalize(images, body_html):
    """Validate and copy the exact assets saved in the confirmed snapshot.

    The magic signature binds MIME type, not visual correctness or full codec
    validation. General attachments and SVG are intentionally not supported.
    """
    if not isinstance(images, list) or len(images) > MAX_COUNT:
        raise ValueError('Lista de imagens internas inválida ou acima do limite.')
    if not isinstance(body_html, str) or len(body_html) > 200000:
        raise ValueError('HTML de imagens internas inválido ou acima do limite.')
    parser = _References(); parser.feed(body_html); parser.close()
    clean, identifiers, total = [], set(), 0
    for item in images:
        if not isinstance(item, dict) or set(item) - {'contentId', 'contentType', 'contentBase64', 'name'}:
            raise ValueError('Campos de imagem interna inválidos.')
        identifier, kind, encoded = (item.get(k) for k in ('contentId', 'contentType', 'contentBase64'))
        if not isinstance(identifier, str) or not CID.fullmatch(identifier) or identifier in identifiers:
            raise ValueError('Identificador CID inválido ou duplicado.')
        if not isinstance(kind, str) or kind not in TYPES:
            raise ValueError('Imagem interna aceita somente PNG ou JPEG.')
        if not isinstance(encoded, str) or len(encoded) > ((MAX_BYTES + 2) // 3) * 4:
            raise ValueError('Conteúdo de imagem interna inválido ou acima do limite.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Base64 de imagem interna inválido.') from None
        total += len(raw)
        if not raw or total > MAX_BYTES:
            raise ValueError('Imagens internas excedem o limite de dois MiB.')
        valid = (raw.startswith(b'\x89PNG\r\n\x1a\n') if kind == 'image/png'
                 else raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'))
        if not valid:
            raise ValueError('Assinatura da imagem diverge do tipo declarado.')
        name = item.get('name', identifier.split('@')[0] + TYPES[kind])
        if (not isinstance(name, str) or not 1 <= len(name) <= 120
                or any(ord(c) < 32 or c in '/\\' for c in name)):
            raise ValueError('Nome de imagem interna inválido.')
        clean.append({'contentId': identifier, 'contentType': kind,
                      'contentBase64': base64.b64encode(raw).decode('ascii'), 'name': name})
        identifiers.add(identifier)
    if identifiers != parser.ids:
        raise ValueError('Cada CID do HTML deve corresponder a uma imagem; imagens sem referência são recusadas.')
    return clean


def summaries(images):
    """Preview metadata only; never copy image bytes to audit or telemetry."""
    return [{'contentId': item['contentId'], 'contentType': item['contentType'], 'name': item['name'],
             'bytes': len(base64.b64decode(item['contentBase64'])),
             'sha256': hashlib.sha256(base64.b64decode(item['contentBase64'])).hexdigest()}
            for item in images]


def add_body(message, body, body_html='', images=None):
    """One multipart/related representation shared by SMTP and Gmail API."""
    assets = normalize([] if images is None else images, body_html)
    message.set_content(body)
    if body_html:
        message.add_alternative(body_html, subtype='html')
    if assets:
        related = message.get_payload()[-1]
        for item in assets:
            related.add_related(base64.b64decode(item['contentBase64']), maintype='image',
                subtype=item['contentType'].split('/')[1], cid='<' + item['contentId'] + '>',
                disposition='inline', filename=item['name'])
