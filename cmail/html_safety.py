"""Allowlisted email HTML; no scripts, remote images or executable CSS."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .template_render import LIMIT


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
