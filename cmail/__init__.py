"""CMAIL: rotinas independentes de e-mail."""

__version__ = "26.9.11c"

from .config import Config
from .api import CmailApi, create_api
from .service import MailService, Principal
from .web import create_app, create_blueprint

__all__ = [
    "CmailApi", "Config", "MailService", "Principal", "create_api",
    "create_app", "create_blueprint", "__version__",
]
