"""Opt-in named mailbox composition for trusted hosts; no HTTP/OAuth router."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from collections.abc import Mapping
import re
import threading

from .config import Config, ConfigError, read_config_document, parse_env_pointer
from .principal import Principal


def _connector_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value):
        raise ConfigError('connectorId deve usar 1–64 caracteres ASCII: letra inicial, minúsculas, números, _ ou -.')
    return value


@dataclass(frozen=True)
class ConnectorConfig:
    """Schema 2 composition; child documents retain the native 1.x grammar."""
    config_file: Path
    root: Path
    webmail_connector_id: str
    connectors: Mapping[str, Config]

    @classmethod
    def load(cls, root=None):
        base = Path(root or Path.cwd()).resolve()
        pointer = Path(parse_env_pointer(base / '.env'))
        return cls.from_file(pointer if pointer.is_absolute() else base / pointer, root=base)

    @classmethod
    def from_file(cls, path, *, root=None):
        path = Path(path).resolve()
        raw, _ = read_config_document(path)
        return cls.from_mapping(raw, path=path, root=root)

    @classmethod
    def from_mapping(cls, raw, *, path, root=None):
        path = Path(path).resolve()
        base = Path(root).resolve() if root is not None else path.parent
        if (not isinstance(raw, dict) or set(raw) != {'schemaVersion', 'webmailConnectorId', 'connectors'}
                or raw['schemaVersion'] != '2.0'):
            raise ConfigError('Registro exige schemaVersion 2.0 e contrato fechado de conectores.')
        selected = _connector_id(raw['webmailConnectorId'])
        entries = raw['connectors']
        if not isinstance(entries, dict) or not entries:
            raise ConfigError('connectors deve ser um objeto não vazio.')
        configs, mailboxes = {}, set()
        for key, value in entries.items():
            key = _connector_id(key)
            config = Config.from_mapping(value, path=path, root=base)
            if config.mode in {'setup', 'gmail-file'}:
                raise ConfigError('Registro novo não aceita setup ou gmail-file; use a API legada até o contrato próprio.')
            expected = (base / 'security/cmail/accounts' / key).resolve()
            state_root = (base / 'security/cmail/accounts').resolve()
            if (config.state_dir != expected or not expected.is_relative_to(state_root)
                    or any(expected == old.state_dir or expected.is_relative_to(old.state_dir)
                           or old.state_dir.is_relative_to(expected) for old in configs.values())):
                raise ConfigError('state.directory deve resolver para security/cmail/accounts/<connectorId> na instância.')
            address = (config.google_account if config.mode == 'gmail' else
                       config.microsoft_account if config.mode == 'microsoft' else config.account).casefold()
            mailbox = (config.mode, address)
            if address and mailbox in mailboxes:
                raise ConfigError('Caixa duplicada: aliases exigem decisão explícita, não outro conector.')
            if address:
                mailboxes.add(mailbox)
            configs[key] = config
        if selected not in configs:
            raise ConfigError('webmailConnectorId não existe no registro.')
        if configs[selected].mode == 'microsoft-imap':
            raise ConfigError('Microsoft IMAP é headless; mantenha outro conector no Webmail.')
        return cls(path, base, selected, MappingProxyType(configs))


class BoundMailbox:
    """Native API plus native mail principal, bound to one explicit connector.

    Hosts must supply their already authenticated mailbox principal. This is not
    an authentication mechanism and must not be exposed with free owner input.
    """
    def __init__(self, key, api, principal):
        self.connector_id, self._api, self._principal = key, api, principal
        self._check()

    def _check(self):
        p = self._principal
        if not isinstance(p, Principal) or not p.capabilities:
            raise PermissionError('CMAIL_CONNECTOR_PRINCIPAL_REQUIRED')
        if self._api.service.config.mode == 'gmail-file':
            if p.identity_id or p.email or p.owner_id:
                raise PermissionError('CMAIL_CONNECTOR_PRINCIPAL_MISMATCH')
            return p  # Existing local operator; never fabricate one for a host.
        resolved = self._api.principal_for_owner(p.storage_owner, p.capabilities)
        if (resolved.identity_id != p.identity_id or resolved.email.casefold() != p.email.casefold()
                or resolved.storage_owner != p.storage_owner):
            raise PermissionError('CMAIL_CONNECTOR_PRINCIPAL_MISMATCH')
        return p

    def folders(self):
        return self._api.folders(self._check())

    def messages(self, folder, limit=50):
        return self._api.messages(self._check(), folder, limit)

    def message(self, folder, identifier):
        return self._api.message(self._check(), folder, identifier)

    def attachments(self, identifier):
        return self._api.attachments(self._check(), identifier)

    def attachment(self, identifier, attachment_id):
        return self._api.attachment(self._check(), identifier, attachment_id)

    def annotation_reader(self):
        principal = self._check()
        principal.require('mail.read')
        return self._api.annotation_reader(principal.storage_owner)

    def prepare_send(self, payload):
        return {**self._api.prepare_send(self._check(), payload), 'connectorId': self.connector_id}

    def execute_send(self, draft_id, confirmation_token):
        return self._api.execute_send(self._check(), draft_id, confirmation_token)


class ConnectorRegistry:
    """One lazy native service per connector. No threads, sockets or consent UI."""
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.webmail_connector_id = config.webmail_connector_id
        self._configs = config.connectors
        self._apis = {}
        self._lock = threading.RLock()

    @classmethod
    def from_legacy(cls, api, *, connector_id='legacy'):
        """Reuse the exact mounted service/state/grant without moving any file."""
        key = _connector_id(connector_id)
        instance = cls.__new__(cls)
        instance.config = None
        instance.webmail_connector_id = key
        instance._configs = MappingProxyType({key: api.service.config})
        instance._apis = {key: api}
        instance._lock = threading.RLock()
        return instance

    def _api(self, key):
        key = _connector_id(key)
        if key not in self._configs:
            raise ValueError('CMAIL_CONNECTOR_NOT_FOUND')
        with self._lock:
            if key not in self._apis:
                from .api import CmailApi
                from .service import MailService
                self._apis[key] = CmailApi(MailService(self._configs[key]))
            return self._apis[key]

    def bind(self, connector_id, principal: Principal):
        """No default connector; host resolves the mail principal through native API."""
        return BoundMailbox(connector_id, self._api(connector_id), principal)

    def native_api(self, connector_id):
        """Trusted host adapter for its fixed Webmail; preserves the native API.

        Keep the resulting API server-side. It retains its existing principal
        and capability contract, including the legacy local operator behavior.
        """
        return self._api(connector_id)

    def principal_for_owner(self, connector_id, owner_id, capabilities):
        """Trusted host composition ONLY, same native owner resolver as CmailApi.

        Never expose owner_id or this method as a model/web operation. No added
        grant, fallback identity or default capabilities are created here.
        """
        if not isinstance(capabilities, frozenset) or not capabilities:
            raise ValueError('Capacidades explícitas obrigatórias.')
        return self._api(connector_id).principal_for_owner(owner_id, capabilities)

    def list_connectors(self, principals: Mapping[str, Principal]):
        """Host provides native principals only for connectors it authorized.

        Returns public IDs/provider/capabilities, never paths, addresses or tokens.
        Invalid/expired bindings fail rather than looking like an empty mailbox.
        """
        result = []
        for key, principal in principals.items():
            bound = self.bind(key, principal)
            result.append({'connectorId': key, 'provider': self._configs[key].mode,
                           'capabilities': sorted(bound._principal.capabilities),
                           'webmail': key == self.webmail_connector_id})
        return result
