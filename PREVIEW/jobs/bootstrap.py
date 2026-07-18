"""Worker handler bootstrap and deployment-configured factory loading。"""
from __future__ import annotations

import importlib
from typing import Callable

from sqlalchemy.orm import Session

from app.capabilities.accounts.handler import AccountsSyncHandler
from app.capabilities.devices.handler import DevicesSyncHandler
from app.capabilities.signin_logs.handler import SignInLogsSyncHandler
from app.capabilities.licenses.handler import LicenseAuditSyncHandler
from app.capabilities.app_audit.handler import AppAuditSyncHandler
from app.capabilities.software.handler import SoftwareSyncHandler
from app.capabilities.teams.handler import TeamsSyncHandler
from app.capabilities.sharepoint.handler import SharePointSyncHandler
from app.capabilities.defender.handler import DefenderSyncHandler
from app.capabilities.sentinel.handler import SentinelSyncHandler


def load_graph_client_factory(import_path: str) -> Callable:
    if ":" not in import_path:
        raise ValueError("GraphClient factory must use 'module:attribute' format")
    module_name, attribute_name = import_path.split(":", 1)
    factory = getattr(importlib.import_module(module_name), attribute_name, None)
    if not callable(factory):
        raise ValueError("Configured GraphClient factory is not callable")
    return factory


def build_handlers(session: Session, graph_client_factory: Callable):
    return {
        "accounts.sync": AccountsSyncHandler(session, graph_client_factory),
        "devices.sync": DevicesSyncHandler(session, graph_client_factory),
        "signin_logs.sync": SignInLogsSyncHandler(session, graph_client_factory),
        "licenses.sync": LicenseAuditSyncHandler(session, graph_client_factory),
        "app_audit.sync": AppAuditSyncHandler(session, graph_client_factory),
        "software.sync": SoftwareSyncHandler(session, graph_client_factory),
        "teams.sync": TeamsSyncHandler(session, graph_client_factory),
        "sharepoint.sync": SharePointSyncHandler(session, graph_client_factory),
        "defender.sync": DefenderSyncHandler(session, graph_client_factory),
        "sentinel.sync": SentinelSyncHandler(session, graph_client_factory),
    }
