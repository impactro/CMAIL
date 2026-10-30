"""Trusted-host configuration editing; no mail principal or HTTP admin endpoint."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from .config import Config, ConfigError, MAX_CONFIG_BYTES, read_config_document

_WRITE_LOCK = threading.RLock()


class ConfigurationConflict(ConfigError):
    """The file changed after the host read it, or another editor holds the lock."""


def _revision(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _resource(name: str) -> bytes:
    return files('cmail').joinpath('defaults').joinpath(name).read_bytes()


@contextmanager
def _edit_lock(path: Path):
    # Keep the sidecar after release: removing it could create two lock identities.
    with _WRITE_LOCK, path.with_name('.' + path.name + '.lock').open('a+b') as lock:
        if not lock.seek(0, os.SEEK_END):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ConfigurationConflict('Configuração ocupada por outro editor.') from exc
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class CmailConfiguration:
    """Host must authorize its administrator before exposing any method here.

    ``active_config`` is the immutable Config held by the running service. Saving
    never replaces that service, reads credentials or performs an OAuth action.
    """

    def __init__(self, path: str | Path, *, root: str | Path | None = None,
                 active_config: Config | None = None):
        self._source_path = Path(path).expanduser().absolute()
        self.path = self._source_path.resolve()
        if self.path.suffix.lower() != '.json':
            raise ConfigError('O arquivo de configuração deve usar extensão .json.')
        self.root = Path(root).resolve() if root is not None else self.path.parent
        self.active_config = active_config
        if active_config is not None and (
            active_config.config_file != self.path or active_config.root != self.root
        ):
            raise ConfigError('Configuração ativa pertence a outra instância/arquivo.')

    @classmethod
    def from_config(cls, config: Config) -> 'CmailConfiguration':
        return cls(config.config_file, root=config.root, active_config=config)

    @property
    def markdown_path(self) -> Path:
        return self.path.with_suffix('.md')

    def describe(self) -> dict[str, object]:
        """Native source metadata, including legacy locations outside config/."""
        return {
            'owner': 'cmail',
            'schemaVersions': ['1.0', '1.1', '1.2', '1.3'],
            'jsonPath': str(self.path), 'markdownPath': str(self.markdown_path),
            'markdownAvailable': self.markdown_path.is_file(),
            'consumers': ['cmail.Config', 'cmail.create_api', 'cmail.web:create_component_app'],
            'application': {
                'mode': 'restart', 'automatic': False,
                'standalone': 'restart-process',
                'embedded': 'recreate-component-or-restart-host',
            },
        }

    def catalog_entry(self, config_root: str | Path, *, consumers=('cmail',),
                      apply_mode='process-restart') -> dict[str, object]:
        """CES catalog v1 file entry. Host aggregates and validates its full catalog."""
        base = Path(config_root).expanduser().absolute()
        if base != base.resolve() or self._source_path != self.path:
            raise ConfigError('Catálogo não aceita symlinks ou aliases de caminho.')
        try:
            relative = self.path.relative_to(base)
        except ValueError:
            raise ConfigError('Migre o JSON explicitamente para a pasta config do host.') from None
        if not base.is_dir() or not relative.parts:
            raise ConfigError('Informe a pasta config do catálogo.')
        if any(part in {'', '.', '..'} or ':' in part or '\\' in part for part in relative.parts):
            raise ConfigError('Caminho inválido no catálogo.')
        if not self.markdown_path.is_file() or self.markdown_path.is_symlink():
            raise ConfigError('Catálogo exige Markdown local com o mesmo nome-base.')
        selected = self.read()
        if not isinstance(consumers, (list, tuple)):
            raise ConfigError('Consumidores devem ser uma lista de IDs.')
        consumer_ids = list(consumers)
        if (not 1 <= len(consumer_ids) <= 32
                or any(not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9-]{0,59}', value)
                       for value in consumer_ids)
                or len(set(consumer_ids)) != len(consumer_ids)):
            raise ConfigError('Consumidores inválidos para o catálogo CES.')
        if not isinstance(apply_mode, str) or apply_mode not in {'component-reload', 'process-restart'}:
            raise ConfigError('Conexão CMAIL exige reload do componente ou restart do processo.')
        path = relative.as_posix()
        if len(path) > 300:
            raise ConfigError('Caminho do catálogo excede 300 caracteres.')
        return {
            'id': 'cmail.settings', 'moduleId': 'cmail', 'path': path,
            'documentation': relative.with_suffix('.md').as_posix(),
            'schemaVersion': str(selected['document']['schemaVersion']),
            'purpose': 'Provedor, servidor, referências de segredo e estado do CMAIL.',
            'consumers': consumer_ids, 'applyMode': apply_mode,
            'editable': True, 'sensitive': False, 'secretPaths': [],
        }

    def validate(self, document: object) -> Config:
        """Same schema and path semantics as Config.from_file; no persistence."""
        return self._prepare(document)[2]

    def _prepare(self, document):
        content = self._encode(document)
        snapshot = json.loads(content)
        selected = Config.from_mapping(snapshot, path=self.path, root=self.root)
        return snapshot, content, selected

    @staticmethod
    def _encode(document: object) -> bytes:
        try:
            content = (json.dumps(document, ensure_ascii=False, indent=2,
                                  allow_nan=False) + '\n').encode('utf-8')
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ConfigError('Configuração deve ser um documento JSON válido.') from exc
        if len(content) > MAX_CONFIG_BYTES:
            raise ConfigError('O JSON de configuração excede 512 KiB.')
        return content

    def _snapshot(self, document, content, selected):
        active = self.active_config
        matches = selected == active if active is not None else None
        return {
            'document': document, 'revision': _revision(content), 'source': self.describe(),
            'saved': True, 'applied': matches, 'pendingRestart': not matches,
            'effective': {
                'known': active is not None, 'matchesSaved': matches,
                'restartRequired': not matches,
                'revision': active.source_revision if active is not None else None,
                'schemaVersion': active.schema_version if active is not None else None,
                'mode': active.mode if active is not None else None,
            },
        }

    def read(self) -> dict[str, object]:
        document, content = read_config_document(self.path)
        selected = Config.from_mapping(document, path=self.path, root=self.root)
        return self._snapshot(document, content, selected)

    def _ensure_markdown(self):
        content = _resource('cmail.config.md')
        try:
            with self.markdown_path.open('xb') as stream:
                stream.write(content)
        except FileExistsError:
            pass  # Preserve instance documentation/notes; do not silently overwrite.

    def initialize(self) -> dict[str, object]:
        """Explicitly create the packaged setup JSON/MD at the host-selected path."""
        document, content, selected = self._prepare(json.loads(_resource('cmail.config.json')))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _edit_lock(self.path):
            if self.path.exists():
                raise ConfigurationConflict('Configuração já existe; leia sua revisão.')
            self._ensure_markdown()
            # Exclusive creation also protects against a non-cooperating initializer.
            with self.path.open('xb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        return self._snapshot(document, content, selected)

    def save(self, document: object, *, expected_revision: str) -> dict[str, object]:
        if not isinstance(expected_revision, str) or not re.fullmatch('[0-9a-f]{64}', expected_revision):
            raise ConfigError('Informe a revisão SHA-256 lida antes da edição.')
        document, content, selected = self._prepare(document)
        with _edit_lock(self.path):
            _current, previous = read_config_document(self.path)
            if _revision(previous) != expected_revision:
                raise ConfigurationConflict('Configuração mudou; leia e revise novamente.')
            self._ensure_markdown()
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.path.parent,
                                                 prefix='.' + self.path.name + '.',
                                                 suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Detect external writers which do not participate in our lock.
                if _revision(read_config_document(self.path)[1]) != expected_revision:
                    raise ConfigurationConflict('Configuração mudou; leia e revise novamente.')
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return self._snapshot(document, content, selected)
