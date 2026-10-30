"""CMAIL public facade; load only the adapters the embedding system requests."""

from importlib import import_module

__version__ = "26.10.30e"

_EXPORTS = {
    'CmailConfiguration': ('configuration', 'CmailConfiguration'),
    'ConfigurationConflict': ('configuration', 'ConfigurationConflict'),
    'Config': ('config', 'Config'),
    'CmailApi': ('api', 'CmailApi'),
    'create_api': ('api', 'create_api'),
    'MailService': ('service', 'MailService'),
    'Principal': ('principal', 'Principal'),
    'create_app': ('web', 'create_app'),
    'CmailComponent': ('component', 'CmailComponent'),
    'create_component': ('component', 'create_component'),
    'render_email_template': ('template_render', 'render_email_template'),
}

__all__ = list(_EXPORTS) + ["__version__"]


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    module, attribute = _EXPORTS[name]
    value = getattr(import_module('.' + module, __name__), attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
