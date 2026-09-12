"""Stable component factory for ASGI hosts."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from .api import CmailApi
from .config import Config
from .service import MailService
from .web import create_app


@dataclass(frozen=True)
class CmailComponent:
    config: Config
    service: MailService
    api: CmailApi

    def application(self) -> FastAPI:
        """Return the same mountable ASGI application used standalone."""
        return create_app(self.config, self.service)


def create_component(config: Config) -> CmailComponent:
    service = MailService(config)
    return CmailComponent(config=config, service=service, api=CmailApi(service))
