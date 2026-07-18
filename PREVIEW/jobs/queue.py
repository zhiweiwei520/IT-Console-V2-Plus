"""Durable JobQueue protocol 與 PostgreSQL queue 實作。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Protocol
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.jobs.models import DurableJob, JobDeadLetter
from app.microsoft.models import ManagedTenant
from app.storage.time_utils import utc_now_naive


class JobQueueError(RuntimeError):
    pass


class JobNotFound(JobQueueError):
    pass


class InvalidJobState(JobQueueError):
    pass


class IdempotencyConflict(JobQueueError):
    pass


class JobQueue(Protocol):
    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        managed_tenant_id=None,
        execution_id=None,
        available_at=None,
        job_version: int = 1,
        max_attempts: int = 5,
        trace_id: str | None = None,
    ) -> str: ...

    def claim(
        self, *, job_types: list[str], worker_id: str, lease_seconds: int,
    ) -> dict[str, Any] | None: ...

    def heartbeat(self, message_id: str, *, worker_id: str, lease_seconds: int) -> None: ...
    def complete(self, message_id: str, *, worker_id: str) -> None: ...
    def abandon(
        self, message_id: str, *, worker_id: str, reason: str, delay_seconds: int = 0,
    ) -> str: ...
    def dead_letter(self, message_id: str, *, worker_id: str, reason: str) -> None: ...


class PgJobQueue:
    """Environment-scoped durable queue；transaction commit 由呼叫端控制。"""

    def __init__(
        self,
        session: Session,
        environment_id,
        *,
        clock: Callable[[], datetime] = utc_now_naive,
    ) -> None:
        self.session = session
        self.environment_id = uuid.UUID(str(environment_id))
        self._clock = clock

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        managed_tenant_id=None,
        execution_id=None,
        available_at=None,
        job_version: int = 1,
        max_attempts: int = 5,
        trace_id: str | None = None,
    ) -> str:
        if not job_type or len(job_type) > 64:
            raise ValueError("job_type must be 1-64 characters")
        if not idempotency_key or len(idempotency_key) > 160:
            raise ValueError("idempotency_key must be 1-160 characters")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        self._assert_safe_payload(payload)

        tenant_id = uuid.UUID(str(managed_tenant_id)) if managed_tenant_id else None
        if tenant_id is not None:
            tenant = self.session.execute(
                select(ManagedTenant.id).where(
                    ManagedTenant.id == tenant_id,
                    ManagedTenant.environment_id == self.environment_id,
                )
            ).scalar_one_or_none()
            if tenant is None:
                raise ValueError("managed_tenant_id does not belong to this environment")

        existing = self._find_by_idempotency_key(idempotency_key)
        if existing is not None:
            self._assert_idempotent_match(existing, job_type, payload, tenant_id, execution_id, job_version)
            return str(existing.id)

        now = self._clock()
        job = DurableJob(
            id=uuid.uuid4(),
            environment_id=self.environment_id,
            managed_tenant_id=tenant_id,
            execution_id=uuid.UUID(str(execution_id)) if execution_id else None,
            schema_version=1,
            job_type=job_type,
            job_version=job_version,
            payload=payload,
            idempotency_key=idempotency_key,
            status="queued",
            attempt=0,
            max_attempts=max_attempts,
            available_at=available_at or now,
            trace_id=trace_id,
            requested_at=now,
            updated_at=now,
        )
        try:
            with self.session.begin_nested():
                self.session.add(job)
                self.session.flush()
        except IntegrityError:
            existing = self._find_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            self._assert_idempotent_match(existing, job_type, payload, tenant_id, execution_id, job_version)
            return str(existing.id)
        return str(job.id)

    def claim(
        self, *, job_types: list[str], worker_id: str, lease_seconds: int,
    ) -> dict[str, Any] | None:
        if not job_types or not worker_id or lease_seconds < 1:
            raise ValueError("job_types, worker_id and positive lease_seconds are required")
        now = self._clock()
        claimable = or_(
            DurableJob.status == "queued",
            and_(DurableJob.status == "leased", DurableJob.lease_expires_at <= now),
        )
        job = self.session.execute(
            select(DurableJob)
            .where(
                DurableJob.environment_id == self.environment_id,
                DurableJob.job_type.in_(job_types),
                DurableJob.available_at <= now,
                claimable,
            )
            .order_by(DurableJob.available_at, DurableJob.requested_at, DurableJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = "leased"
        job.attempt += 1
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        self.session.flush()
        return self._envelope(job)

    def heartbeat(self, message_id: str, *, worker_id: str, lease_seconds: int) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        job = self._owned_lease(message_id, worker_id)
        now = self._clock()
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.updated_at = now

    def complete(self, message_id: str, *, worker_id: str) -> None:
        job = self._owned_lease(message_id, worker_id)
        now = self._clock()
        job.status = "completed"
        job.completed_at = now
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = now

    def abandon(
        self,
        message_id: str,
        *,
        worker_id: str,
        reason: str,
        delay_seconds: int = 0,
    ) -> str:
        if delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")
        job = self._owned_lease(message_id, worker_id)
        if job.attempt >= job.max_attempts:
            self._move_to_dead_letter(job, reason)
            return "dead_letter"
        now = self._clock()
        job.status = "queued"
        job.available_at = now + timedelta(seconds=delay_seconds)
        job.lease_owner = None
        job.lease_expires_at = None
        job.last_error = reason[:512]
        job.updated_at = now
        return "queued"

    def dead_letter(self, message_id: str, *, worker_id: str, reason: str) -> None:
        job = self._owned_lease(message_id, worker_id)
        self._move_to_dead_letter(job, reason)

    def _find_by_idempotency_key(self, key: str) -> DurableJob | None:
        return self.session.execute(
            select(DurableJob).where(
                DurableJob.environment_id == self.environment_id,
                DurableJob.idempotency_key == key,
            )
        ).scalar_one_or_none()

    def _get_job(self, message_id: str) -> DurableJob:
        try:
            job_id = uuid.UUID(str(message_id))
        except ValueError as exc:
            raise JobNotFound("job not found") from exc
        job = self.session.execute(
            select(DurableJob).where(
                DurableJob.id == job_id,
                DurableJob.environment_id == self.environment_id,
            )
        ).scalar_one_or_none()
        if job is None:
            raise JobNotFound("job not found")
        return job

    def _owned_lease(self, message_id: str, worker_id: str) -> DurableJob:
        job = self._get_job(message_id)
        now = self._clock()
        if (
            job.status != "leased"
            or job.lease_owner != worker_id
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        ):
            raise InvalidJobState("worker does not hold an active lease")
        return job

    def _move_to_dead_letter(self, job: DurableJob, reason: str) -> None:
        now = self._clock()
        self.session.add(JobDeadLetter(
            job_id=job.id,
            environment_id=job.environment_id,
            managed_tenant_id=job.managed_tenant_id,
            job_type=job.job_type,
            payload=job.payload,
            attempts=job.attempt,
            reason=reason[:512],
            dead_lettered_at=now,
        ))
        job.status = "dead_letter"
        job.last_error = reason[:512]
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = now

    @staticmethod
    def _assert_idempotent_match(existing, job_type, payload, tenant_id, execution_id, job_version) -> None:
        normalized_execution = uuid.UUID(str(execution_id)) if execution_id else None
        if (
            existing.job_type != job_type
            or existing.payload != payload
            or existing.managed_tenant_id != tenant_id
            or existing.execution_id != normalized_execution
            or existing.job_version != job_version
        ):
            raise IdempotencyConflict("idempotency key was already used for different work")

    @staticmethod
    def _envelope(job: DurableJob) -> dict[str, Any]:
        return {
            "schema_version": job.schema_version,
            "message_id": str(job.id),
            "environment_id": str(job.environment_id),
            "managed_tenant_id": str(job.managed_tenant_id) if job.managed_tenant_id else None,
            "execution_id": str(job.execution_id) if job.execution_id else None,
            "job_type": job.job_type,
            "job_version": job.job_version,
            "attempt": job.attempt,
            "trace_id": job.trace_id,
            "requested_at": job.requested_at.isoformat(timespec="microseconds") + "Z",
            "payload": job.payload,
        }

    @classmethod
    def _assert_safe_payload(cls, value: Any) -> None:
        forbidden = {
            "access_token", "refresh_token", "authorization", "password", "secret", "credential",
        }
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower().replace("-", "_") in forbidden:
                    raise ValueError(f"queue payload contains forbidden field: {key}")
                cls._assert_safe_payload(child)
        elif isinstance(value, list):
            for child in value:
                cls._assert_safe_payload(child)
