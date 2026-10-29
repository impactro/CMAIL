"""Independent mail stationery/signatures with explicit, owner-scoped inheritance."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import copy
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from .inline_images import normalize as normalize_images
from .template_render import PLACEHOLDER, LIMIT

KINDS = ("new", "reply", "forward")
CHOICES = {"inherit", "none", "default", "custom"}
FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
BASE_FIELDS = {"sender_name": "", "sender_role": "", "sender_phone": "",
               "sender_email": "", "company_name": "", "header_bg": "#243447",
               "header_accent": "#4d7c99", "footer_notice": ""}
DEFAULT_SIGNATURE = ('<div style="margin-top:24px;border-top:1px solid #d7e2ee;padding-top:14px;'
                     'font-family:Arial,sans-serif;color:#334155;font-size:13px;line-height:1.6">'
                     '{{logo_html}}<strong>{{sender_name}}</strong><br>{{sender_role}}<br>{{company_name}}<br>'
                     '{{sender_phone}}<br>{{sender_email}}</div>')
DEFAULT_TEMPLATE = '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title></head>
<body style="margin:0;background:#eef2f6;font-family:Arial,sans-serif;color:#1f2937">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f6;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:720px;background:#ffffff;border:1px solid #d7e2ee">
<tr><td style="background:{{header_bg}};color:#ffffff;padding:22px 26px"><div style="font-size:12px">{{company_name}}</div><h1 style="margin:6px 0 0;font-size:24px;line-height:1.3">{{title}}</h1></td></tr>
<tr><td height="4" style="background:{{header_accent}};font-size:0">&nbsp;</td></tr>
<tr><td style="padding:26px;font-size:15px;line-height:1.65">{{body_html}}{{signature_html}}</td></tr>
<tr><td style="padding:12px 26px;background:#f8fafc;color:#64748b;font-size:11px">{{footer_notice}}</td></tr>
</table>{{reply_quote_html}}</td></tr></table></body></html>'''


class MailHtml(HTMLParser):
    """Small email HTML allowlist; reject active content rather than trusting uploads."""
    tags = set('html head body title meta table tbody thead tfoot tr td th caption col colgroup '
               'div span p br hr strong b em i u s small font h1 h2 h3 h4 h5 h6 ul ol li '
               'blockquote pre code a img center'.split())
    attrs = set('style class id role lang charset name content width height align valign bgcolor '
                'cellspacing cellpadding border colspan rowspan face size color alt title nowrap href src http-equiv'.split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_decl(self, decl):
        self.output.append('<!doctype html>')

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            raise ValueError('HTML de e-mail contém uma tag não permitida: ' + tag)
        safe = []
        for name, raw in attrs:
            value = raw or ''
            if name not in self.attrs:
                raise ValueError('Atributo HTML não permitido: ' + name)
            if name == 'style' and (re.search(r'url\s*\(|expression|@|\\|[<>]|behavior|binding', value, re.I)
                                     or any(ord(c) < 32 and c not in '\r\n\t' for c in value)):
                raise ValueError('CSS de e-mail não permitido.')
            if name == 'href':
                if any(ord(c) < 33 for c in value) or urlsplit(value).scheme.lower() not in {'https', 'http', 'mailto', 'tel'}:
                    raise ValueError('Link de e-mail inválido.')
            if name == 'src' and (tag != 'img' or not re.fullmatch(r'cid:[A-Za-z0-9_.-]+', value)):
                raise ValueError('Imagens do template devem usar cid: e arquivos incorporados.')
            if tag == 'meta' and name == 'name' and value.lower() != 'viewport':
                raise ValueError('Metadado HTML não permitido.')
            if name == 'http-equiv' and (tag != 'meta' or value.lower() != 'content-type'):
                raise ValueError('Apenas o metadado legado Content-Type é permitido.')
            safe.append(f' {name}="{html.escape(value, quote=True)}"')
        self.output.append('<' + tag + ''.join(safe) + '>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in self.tags:
            raise ValueError('Tag HTML não permitida: ' + tag)
        self.output.append('</' + tag + '>')

    def handle_data(self, data):
        self.output.append(html.escape(data, quote=False))


def safe_html(source):
    if not isinstance(source, str) or len(source) > LIMIT:
        raise ValueError('HTML inválido ou acima do limite.')
    parser = MailHtml()
    parser.feed(source)
    parser.close()
    return ''.join(parser.output)


def substitute(source, fields, html_fields):
    residue = PLACEHOLDER.sub('', source)
    if any(marker in residue for marker in ('{{', '}}', '{%', '{#')):
        raise ValueError('Use somente campos {{nome}} no template.')
    def replace(match):
        name = match.group(1)
        if name in html_fields:
            return html_fields[name]
        if name not in fields:
            raise ValueError('Campo de mesclagem ausente: ' + name)
        return html.escape(fields[name], quote=True)
    return safe_html(PLACEHOLDER.sub(replace, source))


def relative_file(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute() or ':' in name:
        raise ValueError('Informe um arquivo relativo à pasta do template.')
    resolved = (root / name).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Arquivo fora da pasta do template.')
    return resolved


def read_text(path, limit=LIMIT * 4):
    try:
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
    except OSError:
        raise ValueError('Arquivo de aparência ausente ou inacessível: ' + path.name) from None
    if len(data) > limit:
        raise ValueError('Arquivo de template acima do limite.')
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('O arquivo deve estar em UTF-8.') from None


def validate_profile(value):
    if not isinstance(value, dict) or set(value) - {'schemaVersion', 'modes', 'fields', 'templateHtml',
                                                    'signatureHtml', 'templateFile', 'signatureFile', 'assets'}:
        raise ValueError('Perfil de aparência inválido.')
    if value.get('schemaVersion', '1.0') != '1.0':
        raise ValueError('schemaVersion de aparência deve ser 1.0.')
    modes = value.get('modes', {})
    if not isinstance(modes, dict) or set(modes) - set(KINDS):
        raise ValueError('Tipos de mensagem inválidos.')
    for selected in modes.values():
        if not isinstance(selected, dict) or set(selected) - {'template', 'signature'} or any(not isinstance(v, str) or v not in CHOICES for v in selected.values()):
            raise ValueError('Escolha herdar, nenhum, padrão ou personalizado.')
    fields = value.get('fields', {})
    if not isinstance(fields, dict) or len(fields) > 100:
        raise ValueError('Campos de mesclagem inválidos.')
    for key, item in fields.items():
        if not FIELD.fullmatch(key) or key in {'body_html', 'signature_html', 'reply_quote_html', 'logo_html', 'title'} or not isinstance(item, str) or len(item) > 10000:
            raise ValueError('Campo de mesclagem inválido: ' + str(key))
        if key in {'header_bg', 'header_accent'} and not re.fullmatch(r'#[0-9a-fA-F]{6}', item):
            raise ValueError('A cor deve estar no formato #RRGGBB.')
    for kind in ('template', 'signature'):
        source = value.get(kind + 'Html')
        if source is not None:
            if not isinstance(source, str) or len(source) > LIMIT:
                raise ValueError('HTML inválido ou acima do limite.')
            # Substitute placeholders for structural validation without resolving profile defaults.
            safe_html(PLACEHOLDER.sub('https://example.test', source))
        if source is not None and value.get(kind + 'File'):
            raise ValueError('Informe HTML ou arquivo para cada modelo, não ambos.')
    assets = value.get('assets', [])
    if not isinstance(assets, list) or len(assets) > 8:
        raise ValueError('São permitidas até oito imagens por perfil.')
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) - {'contentId', 'file', 'contentType', 'contentBase64', 'name'}:
            raise ValueError('Arquivo de imagem inválido.')
        if bool(asset.get('file')) == bool(asset.get('contentBase64')):
            raise ValueError('Informe arquivo ou conteúdo da imagem.')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', str(asset.get('contentId', ''))):
            raise ValueError('CID inválido.')
    if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 4 * 1024 * 1024:
        raise ValueError('Perfil de aparência acima do limite de quatro MiB.')
    return value


def preview_html(packet):
    output = packet.get('bodyHtml') or '<pre>' + html.escape(packet['body']) + '</pre>'
    for asset in packet.get('inlineImages', []):
        output = output.replace('src="cid:' + asset['contentId'] + '"',
                                'src="data:' + asset['contentType'] + ';base64,' + asset['contentBase64'] + '"')
    return output


class Appearance:
    def __init__(self, root, state_dir, *, company_root=None, workspace_resolver=None):
        self.root = Path(root)
        self.state_dir = Path(state_dir)
        self.company_root = Path(company_root) if company_root else self.root / 'mail' / 'company'
        self.workspace_resolver = workspace_resolver

    def user_root(self, owner):
        if self.workspace_resolver:
            return Path(self.workspace_resolver(owner)).resolve() / 'mail'
        if not owner:
            return self.root / 'mail' / 'personal'
        return self.state_dir / 'workspaces' / hashlib.sha256(owner.encode()).hexdigest() / 'mail'

    def _load(self, root):
        path = root / 'profile.json'
        if not path.is_file():
            return {}
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Perfil fora da pasta de aparência.')
        value = json.loads(read_text(path, 4 * 1024 * 1024))
        return validate_profile(value)

    def _layers(self, owner, override=None):
        return [(self.company_root, self._load(self.company_root), 'company'),
                (self.user_root(owner), validate_profile(override) if override is not None else self._load(self.user_root(owner)), 'personal')]

    def settings(self, owner):
        layers = self._layers(owner)
        resolved = {}
        for kind in KINDS:
            resolved[kind] = {slot: self._selection(layers, kind, slot)[1] for slot in ('template', 'signature')}
        return {'profile': layers[-1][1], 'effective': resolved,
                'companyConfigured': bool(layers[0][1]),
                'workspaceDirectory': str(self.user_root(owner)),
                'defaultTemplateHtml': DEFAULT_TEMPLATE, 'defaultSignatureHtml': DEFAULT_SIGNATURE}

    @staticmethod
    def _selection(layers, kind, slot):
        choice = 'default' if slot == 'signature' or kind == 'new' else 'none'
        source = 'system'
        selected = None
        for root, layer, origin in layers:
            next_choice = layer.get('modes', {}).get(kind, {}).get(slot, 'inherit')
            if next_choice != 'inherit':
                choice, source, selected = next_choice, origin, (root, layer)
        return (choice, selected), {'choice': choice, 'source': source}

    def save(self, owner, profile):
        profile = validate_profile(profile)
        self._assets(self.user_root(owner), profile)
        # Validate every effective context and read asset bytes before publishing any change.
        for kind in KINDS:
            self.render(owner, 'Prévia do e-mail', 'Mensagem de exemplo.', kind=kind, override=profile)
        root = self.user_root(owner)
        root.mkdir(parents=True, exist_ok=True)
        profile = copy.deepcopy(profile)
        for item in profile.get('assets', []):
            if not item.get('contentBase64'):
                continue
            data = base64.b64decode(item['contentBase64'], validate=True)
            extension = '.png' if item['contentType'] == 'image/png' else '.jpg'
            relative = 'assets/' + hashlib.sha256(data).hexdigest() + extension
            destination = relative_file(root, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, staging = tempfile.mkstemp(prefix='.image-', dir=destination.parent)
            try:
                with os.fdopen(file_descriptor, 'wb') as stream:
                    stream.write(data)
                os.replace(staging, destination)
            finally:
                if os.path.exists(staging):
                    os.unlink(staging)
            item.pop('contentBase64')
            item['file'] = relative
        descriptor, temporary = tempfile.mkstemp(prefix='.profile-', suffix='.tmp', dir=root)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(profile, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, root / 'profile.json')
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.settings(owner)

    @staticmethod
    def _assets(root, layer):
        assets = []
        for item in layer.get('assets', []):
            if item.get('file'):
                path = relative_file(root, item['file'])
                try:
                    with path.open('rb') as stream:
                        data = stream.read(2097153)
                except OSError:
                    raise ValueError('Arquivo de imagem ausente: ' + path.name) from None
                mime = 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
                asset = {'contentId': item['contentId'], 'contentType': mime,
                         'contentBase64': base64.b64encode(data).decode(), 'name': item.get('name') or path.name}
            else:
                asset = dict(item)
            assets.append(asset)
        references = ''.join('<img src="cid:' + item['contentId'] + '">' for item in assets)
        return normalize_images(assets, references)

    def render(self, owner, subject, body, *, kind='new', identity=None, override=None, choices=None, values=None):
        if kind not in KINDS or not isinstance(body, str) or not body.strip() or len(body) > LIMIT:
            raise ValueError('Tipo ou corpo de mensagem inválido.')
        layers = self._layers(owner, override)
        fields = {**BASE_FIELDS, **(identity or {})}
        for _, layer, _ in layers:
            fields.update(layer.get('fields', {}))
        if values:
            validate_profile({'fields': values})
            fields.update(values)
        fields['title'] = str(subject)
        sources, assets = {}, {}
        html_slots = {'body_html': '<p>' + html.escape(body).replace('\n', '<br>\n') + '</p>',
                      'signature_html': '', 'reply_quote_html': '', 'logo_html': ''}
        for root, layer, _ in layers:
            if any(item['contentId'] == 'logo' for item in layer.get('assets', [])):
                assets['logo'] = next(item for item in self._assets(root, layer) if item['contentId'] == 'logo')
                html_slots['logo_html'] = '<img src="cid:logo" alt="Logo" width="160" style="display:block;margin-bottom:12px;border:0">'
        signature_text = ''
        if choices is not None and (not isinstance(choices, dict) or set(choices) - {'template', 'signature'} or any(not isinstance(v, str) or v not in CHOICES for v in choices.values())):
            raise ValueError('Seleção de aparência inválida.')
        template_source = ''
        for slot, builtin in (('signature', DEFAULT_SIGNATURE), ('template', DEFAULT_TEMPLATE)):
            (choice, selected), origin = self._selection(layers, kind, slot)
            explicit = (choices or {}).get(slot, 'inherit')
            if explicit != 'inherit':
                choice = explicit
                if choice == 'custom':
                    selected = (layers[-1][0], layers[-1][1])
                origin = {'choice': choice, 'source': 'message'}
            sources[slot] = origin
            if choice == 'none':
                continue
            source = builtin
            if choice == 'custom':
                if selected is None:
                    raise ValueError('Modelo personalizado ausente.')
                root, layer = selected
                source = layer.get(slot + 'Html')
                if source is None and layer.get(slot + 'File'):
                    source = read_text(relative_file(root, layer[slot + 'File']))
                if not source:
                    raise ValueError('Informe o HTML ou arquivo da ' + slot + '.')
                for asset in self._assets(root, layer):
                    identifier = asset['contentId']
                    if identifier in assets and assets[identifier] != asset:
                        raise ValueError('Imagens com o mesmo CID têm conteúdos diferentes.')
                    assets[identifier] = asset
            if slot == 'signature':
                html_slots['signature_html'] = substitute(source, fields, {'logo_html':html_slots['logo_html']})
                plain = re.sub(r'<(?:br\s*/?|/div|/p)>', '\n', html_slots['signature_html'], flags=re.I)
                signature_text = html.unescape(re.sub(r'<[^>]+>', '', plain)).strip()
            else:
                template_source = source
        if template_source:
            if len(re.findall(r'{{\s*body_html\s*}}', template_source)) != 1:
                raise ValueError('O template deve conter exatamente um {{body_html}}.')
            if len(re.findall(r'{{\s*signature_html\s*}}', template_source)) > 1:
                raise ValueError('A assinatura só pode aparecer uma vez.')
            if html_slots['signature_html'] and not re.search(r'{{\s*signature_html\s*}}', template_source):
                html_slots['body_html'] += html_slots['signature_html']
            rendered = substitute(template_source, fields, html_slots)
        else:
            rendered = safe_html(html_slots['body_html'] + html_slots['signature_html'])
        used = set(re.findall(r'src="cid:([A-Za-z0-9_.-]+)"', rendered))
        images = normalize_images([item for key, item in assets.items() if key in used], rendered)
        packet = {'body': body + ('\n\n' + signature_text if signature_text else ''), 'bodyHtml': rendered,
                  'inlineImages': images, 'appearanceSources': sources}
        if len(packet['body']) > LIMIT or len(rendered) > LIMIT:
            raise ValueError('Mensagem final acima do limite.')
        return packet
