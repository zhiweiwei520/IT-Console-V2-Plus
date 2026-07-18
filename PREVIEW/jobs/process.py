"""Worker process polling loop and graceful drain。"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.jobs.models import DurableJob
from app.jobs.worker import WorkerRunner
from app.storage.time_utils import utc_now_naive

logger = logging.getLogger(__name__)


class WorkerProcess:
    """一次只執行一個 job；stop 後停止 claim，等待目前 job 結束再退出。"""

    def __init__(
        self,
        session: Session,
        runner: WorkerRunner,
        *,
        poll_seconds: float = 2.0,
        metrics_callback: Callable[[dict], None] | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.session = session
        self.runner = runner
        self.poll_seconds = poll_seconds
        self.metrics_callback = metrics_callback
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    async def run_cycle(self) -> int:
        processed = 0
        for environment_id in self._claimable_environment_ids():
            if self._stop_requested:
                break
            if await self.runner.run_once(environment_id):
                processed += 1
        self._emit_metrics()
        return processed

    async def run_forever(self) -> None:
        logger.info("worker_started worker_id=%s", self.runner.worker_id)
        while not self._stop_requested:
            processed = await self.run_cycle()
            if processed == 0 and not self._stop_requested:
                await self._interruptible_sleep()
        self._emit_metrics()
        logger.info("worker_stopped worker_id=%s", self.runner.worker_id)

    def _claimable_environment_ids(self):
        now = utc_now_naive()
        rows = self.session.execute(
            select(DurableJob.environment_id)
            .where(
                DurableJob.job_type.in_(list(self.runner.handlers)),
                DurableJob.available_at <= now,
                or_(
                    DurableJob.status == "queued",
                    and_(
                        DurableJob.status == "leased",
                        DurableJob.lease_expires_at <= now,
                    ),
                ),
            )
            .distinct()
            .order_by(DurableJob.environment_id)
        ).scalars().all()
        self.session.rollback()
        return rows

    async def _interruptible_sleep(self) -> None:
        remaining = self.poll_seconds
        while remaining > 0 and not self._stop_requested:
            step = min(remaining, 0.25)
            await asyncio.sleep(step)
            remaining -= step

    def _emit_metrics(self) -> None:
        if self.metrics_callback is not None:
            self.metrics_callback(self.runner.metrics.snapshot())
