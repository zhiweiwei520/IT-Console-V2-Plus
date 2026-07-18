"""Framework-independent durable worker runner。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.queue import PgJobQueue
from app.microsoft.models import ManagedTenant
from app.platform.models import EnvironmentMembership, ManagementEnvironment
from app.storage.time_utils import utc_now_naive


@dataclass
class WorkerMetrics:
    started_at: datetime = field(default_factory=utc_now_naive)
    claimed: int = 0
    completed: int = 0
    retried: int = 0
    dead_lettered: int = 0
    unexpected_errors: int = 0
    active_jobs: int = 0
    last_job_at: datetime | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(timespec="seconds") + "Z",
            "claimed": self.claimed,
            "completed": self.completed,
            "retried": self.retried,
            "dead_lettered": self.dead_lettered,
            "unexpected_errors": self.unexpected_errors,
            "active_jobs": self.active_jobs,
            "last_job_at": (
                self.last_job_at.isoformat(timespec="seconds") + "Z" if self.last_job_at else None
            ),
        }


class RetryableJobError(RuntimeError):
    def __init__(self, code: str, *, delay_seconds: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.delay_seconds = delay_seconds


class TerminalJobError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JobHandler(Protocol):
    async def handle(
        self,
        envelope: dict[str, Any],
        *,
        queue: PgJobQueue,
        worker_id: str,
        lease_seconds: int,
    ) -> None: ...


class WorkerRunner:
    def __init__(
        self,
        session: Session,
        handlers: dict[str, JobHandler],
        *,
        worker_id: str,
        lease_seconds: int = 300,
        metrics: WorkerMetrics | None = None,
    ) -> None:
        if not handlers:
            raise ValueError("at least one job handler is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self.session = session
        self.handlers = handlers
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.metrics = metrics or WorkerMetrics()

    async def run_once(self, environment_id) -> bool:
        queue = PgJobQueue(self.session, environment_id)
        envelope = queue.claim(
            job_types=list(self.handlers),
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if envelope is None:
            self.session.rollback()
            return False
        self.session.commit()  # lease 必須在外部 I/O 前 durable
        self.metrics.claimed += 1
        self.metrics.active_jobs = 1
        self.metrics.last_job_at = utc_now_naive()

        try:
            self._revalidate_scope(envelope)
            handler = self.handlers[envelope["job_type"]]
            await handler.handle(
                envelope,
                queue=queue,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            queue.complete(envelope["message_id"], worker_id=self.worker_id)
            self.session.commit()
            self.metrics.completed += 1
        except RetryableJobError as exc:
            self.session.rollback()
            status = queue.abandon(
                envelope["message_id"],
                worker_id=self.worker_id,
                reason=exc.code,
                delay_seconds=exc.delay_seconds,
            )
            self.session.commit()
            if status == "dead_letter":
                self.metrics.dead_lettered += 1
            else:
                self.metrics.retried += 1
        except TerminalJobError as exc:
            self.session.rollback()
            queue.dead_letter(
                envelope["message_id"], worker_id=self.worker_id, reason=exc.code,
            )
            self.session.commit()
            self.metrics.dead_lettered += 1
        except Exception:
            self.session.rollback()
            status = queue.abandon(
                envelope["message_id"],
                worker_id=self.worker_id,
                reason="unexpected_worker_error",
            )
            self.session.commit()
            self.metrics.unexpected_errors += 1
            if status == "dead_letter":
                self.metrics.dead_lettered += 1
            else:
                self.metrics.retried += 1
        finally:
            self.metrics.active_jobs = 0
        return True

    def _revalidate_scope(self, envelope: dict[str, Any]) -> None:
        environment_id = uuid.UUID(envelope["environment_id"])
        tenant_raw = envelope.get("managed_tenant_id")
        membership_raw = envelope.get("payload", {}).get("requested_membership_id")
        environment = self.session.execute(
            select(ManagementEnvironment).where(
                ManagementEnvironment.id == environment_id,
                ManagementEnvironment.status == "active",
            )
        ).scalar_one_or_none()
        if environment is None:
            raise TerminalJobError("environment_inactive")
        if not tenant_raw:
            raise TerminalJobError("managed_tenant_missing")
        tenant = self.session.execute(
            select(ManagedTenant).where(
                ManagedTenant.id == uuid.UUID(tenant_raw),
                ManagedTenant.environment_id == environment_id,
                ManagedTenant.status.in_(("active", "degraded")),
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise TerminalJobError("managed_tenant_unavailable")
        if not membership_raw:
            raise TerminalJobError("membership_snapshot_missing")
        membership = self.session.execute(
            select(EnvironmentMembership).where(
                EnvironmentMembership.id == uuid.UUID(membership_raw),
                EnvironmentMembership.environment_id == environment_id,
                EnvironmentMembership.status == "active",
            )
        ).unique().scalar_one_or_none()
        # 慣例：sync job 的 job_type 與其所需權限 code 同名（accounts.sync / devices.sync）。
        # 不得寫死單一 capability，否則新增模組時會拿錯權限重驗證（見 bootstrap.build_handlers）。
        required_permission = envelope["job_type"]
        if membership is None or required_permission not in membership.permission_codes:
            raise TerminalJobError("membership_no_longer_authorized")
        tenant_id = uuid.UUID(tenant_raw)
        if not membership.all_managed_tenants and not any(
            grant.managed_tenant_id == tenant_id for grant in membership.tenant_grants
        ):
            raise TerminalJobError("managed_tenant_grant_revoked")
