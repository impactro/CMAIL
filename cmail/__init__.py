"""CMAIL: rotinas independentes de e-mail."""

__version__ = "26.9.13a"

from .config import Config
from .api import CmailApi, create_api
from .service import MailService, Principal
from .web import create_app
from .component import CmailComponent, create_component

__all__ = [
    "CmailApi", "Config", "MailService", "Principal", "create_api",
    "CmailComponent", "create_app", "create_component", "__version__",
]
