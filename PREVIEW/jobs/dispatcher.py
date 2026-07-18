"""Capability job dispatchers；outbox 與 audit 由呼叫端同一 transaction commit。"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.queue import PgJobQueue
from app.microsoft.models import ManagedTenant
from app.platform.audit import record_audit
from app.storage.tenant_context import TenantContext


class AccountsSyncDispatcher:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context

    def enqueue(self, managed_tenant_id, *, operation_id=None, trace_id=None) -> str:
        if not self.context.has_permission("accounts.sync"):
            raise PermissionError("accounts.sync required")
        tenant_id = uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id):
            raise PermissionError("managed tenant not in grant")
        tenant = self.session.execute(
            select(ManagedTenant).where(
                ManagedTenant.id == tenant_id,
                ManagedTenant.environment_id == self.context.environment_id,
                ManagedTenant.status.in_(("active", "degraded")),
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError("managed tenant is unavailable")

        operation = uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
        queue = PgJobQueue(self.session, self.context.environment_id)
        message_id = queue.enqueue(
            "accounts.sync",
            {"requested_membership_id": str(self.context.membership_id), "mode": "full"},
            idempotency_key=f"manual:{operation}:accounts.sync:{tenant_id}:v1",
            managed_tenant_id=tenant_id,
            execution_id=operation,
            trace_id=trace_id or self.context.correlation_id,
        )
        record_audit(
            environment_id=self.context.environment_id,
            actor_principal_id=self.context.principal_id,
            action="accounts.sync.enqueue",
            target_type="managed_tenant",
            target_id=tenant_id,
            correlation_id=self.context.correlation_id,
        )
        return message_id


class DevicesSyncDispatcher:
    """devices.sync 排程；結構刻意與 AccountsSyncDispatcher 平行（roadmap Phase B 尚未定案
    共用模板，B1–B3 驗證後才抽 base，見 roadmap.md Phase B exit gate）。"""

    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context

    def enqueue(self, managed_tenant_id, *, operation_id=None, trace_id=None) -> str:
        if not self.context.has_permission("devices.sync"):
            raise PermissionError("devices.sync required")
        tenant_id = uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id):
            raise PermissionError("managed tenant not in grant")
        tenant = self.session.execute(
            select(ManagedTenant).where(
                ManagedTenant.id == tenant_id,
                ManagedTenant.environment_id == self.context.environment_id,
                ManagedTenant.status.in_(("active", "degraded")),
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError("managed tenant is unavailable")

        operation = uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
        queue = PgJobQueue(self.session, self.context.environment_id)
        message_id = queue.enqueue(
            "devices.sync",
            {"requested_membership_id": str(self.context.membership_id), "mode": "full"},
            idempotency_key=f"manual:{operation}:devices.sync:{tenant_id}:v1",
            managed_tenant_id=tenant_id,
            execution_id=operation,
            trace_id=trace_id or self.context.correlation_id,
        )
        record_audit(
            environment_id=self.context.environment_id,
            actor_principal_id=self.context.principal_id,
            action="devices.sync.enqueue",
            target_type="managed_tenant",
            target_id=tenant_id,
            correlation_id=self.context.correlation_id,
        )
        return message_id


class SignInLogsSyncDispatcher:
    """signin_logs.sync 排程；結構與 Accounts/Devices dispatcher 平行（B1–B3 驗證後才抽 base）。"""

    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context

    def enqueue(self, managed_tenant_id, *, operation_id=None, trace_id=None) -> str:
        if not self.context.has_permission("signin_logs.sync"):
            raise PermissionError("signin_logs.sync required")
        tenant_id = uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id):
            raise PermissionError("managed tenant not in grant")
        tenant = self.session.execute(
            select(ManagedTenant).where(
                ManagedTenant.id == tenant_id,
                ManagedTenant.environment_id == self.context.environment_id,
                ManagedTenant.status.in_(("active", "degraded")),
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError("managed tenant is unavailable")

        operation = uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
        queue = PgJobQueue(self.session, self.context.environment_id)
        message_id = queue.enqueue(
            "signin_logs.sync",
            {"requested_membership_id": str(self.context.membership_id), "mode": "incremental"},
            idempotency_key=f"manual:{operation}:signin_logs.sync:{tenant_id}:v1",
            managed_tenant_id=tenant_id,
            execution_id=operation,
            trace_id=trace_id or self.context.correlation_id,
        )
        record_audit(
            environment_id=self.context.environment_id,
            actor_principal_id=self.context.principal_id,
            action="signin_logs.sync.enqueue",
            target_type="managed_tenant",
            target_id=tenant_id,
            correlation_id=self.context.correlation_id,
        )
        return message_id


class LicenseAuditSyncDispatcher:
    def __init__(self, session, context):
        self.session, self.context = session, context

    def enqueue(self, managed_tenant_id, *, operation_id=None, trace_id=None):
        if not self.context.has_permission("licenses.sync"):
            raise PermissionError("licenses.sync required")
        tenant_id = uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id):
            raise PermissionError("managed tenant not in grant")
        tenant = self.session.execute(select(ManagedTenant).where(ManagedTenant.id == tenant_id, ManagedTenant.environment_id == self.context.environment_id, ManagedTenant.status.in_(("active", "degraded")))).scalar_one_or_none()
        if tenant is None:
            raise ValueError("managed tenant is unavailable")
        operation = uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
        message_id = PgJobQueue(self.session, self.context.environment_id).enqueue("licenses.sync", {"requested_membership_id": str(self.context.membership_id), "mode": "full"}, idempotency_key=f"manual:{operation}:licenses.sync:{tenant_id}:v1", managed_tenant_id=tenant_id, execution_id=operation, trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id, actor_principal_id=self.context.principal_id, action="licenses.sync.enqueue", target_type="managed_tenant", target_id=tenant_id, correlation_id=self.context.correlation_id)
        return message_id

class AppAuditSyncDispatcher:
    def __init__(self, session, context): self.session, self.context = session, context
    def enqueue(self, managed_tenant_id, *, operation_id=None, trace_id=None):
        if not self.context.has_permission("app_audit.sync"): raise PermissionError("app_audit.sync required")
        tenant_id = uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id): raise PermissionError("managed tenant not in grant")
        tenant = self.session.execute(select(ManagedTenant).where(ManagedTenant.id == tenant_id, ManagedTenant.environment_id == self.context.environment_id, ManagedTenant.status.in_(("active", "degraded")))).scalar_one_or_none()
        if tenant is None: raise ValueError("managed tenant is unavailable")
        operation = uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
        message_id = PgJobQueue(self.session, self.context.environment_id).enqueue("app_audit.sync", {"requested_membership_id": str(self.context.membership_id), "mode": "full"}, idempotency_key=f"manual:{operation}:app_audit.sync:{tenant_id}:v1", managed_tenant_id=tenant_id, execution_id=operation, trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id, actor_principal_id=self.context.principal_id, action="app_audit.sync.enqueue", target_type="managed_tenant", target_id=tenant_id, correlation_id=self.context.correlation_id)
        return message_id

class SoftwareSyncDispatcher:
    def __init__(self,session,context): self.session,self.context=session,context
    def enqueue(self,managed_tenant_id,*,operation_id=None,trace_id=None):
        if not self.context.has_permission("software.sync"): raise PermissionError("software.sync required")
        tenant_id=uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id): raise PermissionError("managed tenant not in grant")
        tenant=self.session.execute(select(ManagedTenant).where(ManagedTenant.id==tenant_id,ManagedTenant.environment_id==self.context.environment_id,ManagedTenant.status.in_(("active","degraded")))).scalar_one_or_none()
        if tenant is None: raise ValueError("managed tenant is unavailable")
        operation=uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
        message_id=PgJobQueue(self.session,self.context.environment_id).enqueue("software.sync",{"requested_membership_id":str(self.context.membership_id),"mode":"full"},idempotency_key=f"manual:{operation}:software.sync:{tenant_id}:v1",managed_tenant_id=tenant_id,execution_id=operation,trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id,actor_principal_id=self.context.principal_id,action="software.sync.enqueue",target_type="managed_tenant",target_id=tenant_id,correlation_id=self.context.correlation_id); return message_id
class TeamsSyncDispatcher:
    def __init__(self,session,context): self.session,self.context=session,context
    def enqueue(self,managed_tenant_id,*,operation_id=None,trace_id=None):
        if not self.context.has_permission("teams.sync"): raise PermissionError("teams.sync required")
        tenant_id=uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id): raise PermissionError("managed tenant not in grant")
        tenant=self.session.execute(select(ManagedTenant).where(ManagedTenant.id==tenant_id,ManagedTenant.environment_id==self.context.environment_id,ManagedTenant.status.in_(("active","degraded")))).scalar_one_or_none()
        if tenant is None: raise ValueError("managed tenant is unavailable")
        operation=uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4(); message_id=PgJobQueue(self.session,self.context.environment_id).enqueue("teams.sync",{"requested_membership_id":str(self.context.membership_id),"mode":"quick"},idempotency_key=f"manual:{operation}:teams.sync:{tenant_id}:v1",managed_tenant_id=tenant_id,execution_id=operation,trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id,actor_principal_id=self.context.principal_id,action="teams.sync.enqueue",target_type="managed_tenant",target_id=tenant_id,correlation_id=self.context.correlation_id); return message_id
class SharePointSyncDispatcher:
    def __init__(self,session,context): self.session,self.context=session,context
    def enqueue(self,managed_tenant_id,*,operation_id=None,trace_id=None):
        if not self.context.has_permission("sharepoint.sync"): raise PermissionError("sharepoint.sync required")
        tenant_id=uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id): raise PermissionError("managed tenant not in grant")
        tenant=self.session.execute(select(ManagedTenant).where(ManagedTenant.id==tenant_id,ManagedTenant.environment_id==self.context.environment_id,ManagedTenant.status.in_(("active","degraded")))).scalar_one_or_none()
        if tenant is None: raise ValueError("managed tenant is unavailable")
        operation=uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4(); message_id=PgJobQueue(self.session,self.context.environment_id).enqueue("sharepoint.sync",{"requested_membership_id":str(self.context.membership_id),"mode":"quick"},idempotency_key=f"manual:{operation}:sharepoint.sync:{tenant_id}:v1",managed_tenant_id=tenant_id,execution_id=operation,trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id,actor_principal_id=self.context.principal_id,action="sharepoint.sync.enqueue",target_type="managed_tenant",target_id=tenant_id,correlation_id=self.context.correlation_id); return message_id
class DefenderSyncDispatcher:
    def __init__(self,session,context): self.session,self.context=session,context
    def enqueue(self,managed_tenant_id,*,operation_id=None,trace_id=None):
        if not self.context.has_permission("defender.sync"): raise PermissionError("defender.sync required")
        tenant_id=uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id): raise PermissionError("managed tenant not in grant")
        tenant=self.session.execute(select(ManagedTenant).where(ManagedTenant.id==tenant_id,ManagedTenant.environment_id==self.context.environment_id,ManagedTenant.status.in_(("active","degraded")))).scalar_one_or_none()
        if tenant is None: raise ValueError("managed tenant is unavailable")
        operation=uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4(); message_id=PgJobQueue(self.session,self.context.environment_id).enqueue("defender.sync",{"requested_membership_id":str(self.context.membership_id),"mode":"incremental"},idempotency_key=f"manual:{operation}:defender.sync:{tenant_id}:v1",managed_tenant_id=tenant_id,execution_id=operation,trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id,actor_principal_id=self.context.principal_id,action="defender.sync.enqueue",target_type="managed_tenant",target_id=tenant_id,correlation_id=self.context.correlation_id); return message_id
class SentinelSyncDispatcher:
    def __init__(self,session,context): self.session,self.context=session,context
    def enqueue(self,managed_tenant_id,*,operation_id=None,trace_id=None):
        if not self.context.has_permission("sentinel.sync"): raise PermissionError("sentinel.sync required")
        tenant_id=uuid.UUID(str(managed_tenant_id))
        if not self.context.can_access_tenant(tenant_id): raise PermissionError("managed tenant not in grant")
        tenant=self.session.execute(select(ManagedTenant).where(ManagedTenant.id==tenant_id,ManagedTenant.environment_id==self.context.environment_id,ManagedTenant.status.in_(("active","degraded")))).scalar_one_or_none()
        if tenant is None: raise ValueError("managed tenant is unavailable")
        operation=uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4(); message_id=PgJobQueue(self.session,self.context.environment_id).enqueue("sentinel.sync",{"requested_membership_id":str(self.context.membership_id),"mode":"incremental"},idempotency_key=f"manual:{operation}:sentinel.sync:{tenant_id}:v1",managed_tenant_id=tenant_id,execution_id=operation,trace_id=trace_id or self.context.correlation_id)
        record_audit(environment_id=self.context.environment_id,actor_principal_id=self.context.principal_id,action="sentinel.sync.enqueue",target_type="managed_tenant",target_id=tenant_id,correlation_id=self.context.correlation_id); return message_id
