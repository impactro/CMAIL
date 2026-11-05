"""Bounded host-supplied files; no path/URL resolution or external effects."""
import base64
import binascii
import hashlib
import json
import re

MAX_COUNT = 8
MAX_BYTES = 2 * 1024 * 1024  # Aggregate common files + inline raster assets.
MAX_SNAPSHOT_BYTES = 3 * 1024 * 1024


def normalize(items):
    if not isinstance(items, list) or len(items) > MAX_COUNT:
        raise ValueError('Lista de anexos inválida ou acima de oito arquivos.')
    clean, total = [], 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {'name', 'contentType', 'contentBase64'}:
            raise ValueError('Anexo exige nome, tipo e conteúdo; caminhos e URLs não são aceitos.')
        name, kind, encoded = (item[k] for k in ('name', 'contentType', 'contentBase64'))
        if (not isinstance(name, str) or not 1 <= len(name) <= 120 or name in {'.', '..'}
                or any(ord(c) < 32 or ord(c) == 127 or c in '/\\' for c in name)):
            raise ValueError('Nome de anexo inválido.')
        if not isinstance(kind, str) or not re.fullmatch(r'[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*', kind):
            raise ValueError('Tipo MIME de anexo inválido.')
        if not isinstance(encoded, str) or len(encoded) > ((MAX_BYTES + 2)//3)*4:
            raise ValueError('Anexo acima do limite de tamanho.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Base64 de anexo inválido.') from None
        total += len(raw)
        if not raw or total > MAX_BYTES:
            raise ValueError('Anexos vazios ou acima de dois MiB.')
        clean.append({'name': name, 'contentType': kind, 'contentBase64': base64.b64encode(raw).decode('ascii')})
    return clean


def summaries(items):
    return [{'name': a['name'], 'contentType': a['contentType'],
             'bytes': len(base64.b64decode(a['contentBase64'])),
             'sha256': hashlib.sha256(base64.b64decode(a['contentBase64'])).hexdigest()} for a in items]


def validate_snapshot(payload):
    files = normalize(payload.get('attachments', []))
    if not files and not payload.get('attachmentManifest'):
        return
    if summaries(files) != payload.get('attachmentManifest'):
        raise ValueError('Integridade dos anexos diverge da prévia.')
    inline = sum(len(base64.b64decode(a['contentBase64'])) for a in payload.get('inlineImages', []))
    if inline + sum(a['bytes'] for a in summaries(files)) > MAX_BYTES:
        raise ValueError('Anexos e imagens internas excedem dois MiB somados.')
    if len(json.dumps(payload, ensure_ascii=True).encode('utf-8')) > MAX_SNAPSHOT_BYTES:
        raise ValueError('Prévia com anexos excede três MiB serializados.')


def add_files(message, items):
    for item in normalize([] if items is None else items):
        main, sub = item['contentType'].split('/')
        message.add_attachment(base64.b64decode(item['contentBase64']), maintype=main,
                               subtype=sub, filename=item['name'])


def bundle(items, images):
    files = normalize([] if items is None else items)
    size = sum(len(base64.b64decode(a['contentBase64'])) for a in files + images)
    if files and size > MAX_BYTES:
        raise ValueError('Anexos e imagens internas excedem dois MiB somados.')
    return files
