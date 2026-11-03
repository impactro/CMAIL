"""Initial Gmail configuration, authorized by a trusted embedding host."""
import json
import re
import uuid
from urllib.parse import urlsplit

from .configuration import CmailConfiguration, ConfigurationConflict
from .setup import SetupError, _write_secret, _reference


def setup_origin(value):
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        raise ValueError('setupOrigin deve ser uma origem explícita.')
    parsed = urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or
            parsed.fragment or parsed.path or
            not (parsed.scheme == 'https' or parsed.scheme == 'http' and
                 parsed.hostname in {'localhost', '127.0.0.1', '::1'})):
        raise ValueError('setupOrigin exige HTTPS ou HTTP loopback, sem caminho.')
    try:
        parsed.port
    except ValueError:
        raise ValueError('Porta inválida em setupOrigin.') from None
    return value


def callback_uri(origin, prefix):
    if prefix and not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+', prefix):
        raise SetupError('Prefixo de montagem inválido.')
    return origin + prefix + '/auth/google/callback'


def import_client(content, callback):
    if not content or len(content) > 65536:
        raise SetupError('JSON OAuth vazio ou acima de 64 KiB.')
    try:
        value = json.loads(content)
    except (ValueError, UnicodeError):
        raise SetupError('Arquivo OAuth JSON inválido.') from None
    if not isinstance(value, dict) or set(value) != {'web'} or not isinstance(value['web'], dict):
        raise SetupError('Importe um cliente Google Web, não tokens ou cliente Desktop.')
    web = value['web']
    client, secret, redirects = (web.get(key) for key in ('client_id', 'client_secret', 'redirect_uris'))
    if (not isinstance(client, str) or not client.endswith('.apps.googleusercontent.com') or
            len(client) > 255 or any(c.isspace() for c in client) or
            not isinstance(secret, str) or not secret.strip() or len(secret) > 16384 or
            not isinstance(redirects, list) or callback not in redirects or
            any(key in web for key in ('refresh_token', 'access_token', 'token'))):
        raise SetupError('Cliente Web inválido ou callback desta montagem não cadastrado no Google.')
    return client, secret


def save_initial_gmail(config, content, callback, revision):
    client, secret = import_client(content, callback)
    editor = CmailConfiguration.from_config(config)
    snapshot = editor.read()
    if snapshot['revision'] != revision or snapshot['document']['mode'] != 'setup':
        raise ConfigurationConflict('Configuração mudou ou já foi concluída; recarregue o componente.')
    document = snapshot['document']
    document['mode'] = 'gmail'
    path = config.state_dir / 'security/google' / ('client-secret-' + uuid.uuid4().hex + '.txt')
    document['google'] = {'account': '', 'clientId': client,
                          'clientSecretFile': _reference(config, path), 'redirectUri': callback}
    editor.validate(document)
    try:
        _write_secret(path, secret)
        editor.save(document, expected_revision=revision)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
