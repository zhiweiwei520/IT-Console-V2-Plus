"""
單機自架用的內嵌背景 worker。

目的：讓網頁上的「立即同步」按下後由背景執行緒自動處理，操作者不必再另開一個
`manage.py run-worker` CLI process——所有操作都在 web 上完成。

與獨立 worker process 的關係（不衝突、二擇一）：
- 單機自架：內嵌 worker（本檔）預設開啟，隨 web app 一起跑。
- 水平擴充／要獨立部署 worker：設 `V2PLUS_EMBEDDED_WORKER=false` 停用內嵌 worker，
  改跑一個或多個 `manage.py run-worker`。durable queue 的 lease／idempotency／SKIP LOCKED
  保證對「內嵌執行緒」或「獨立 process」皆成立，內嵌不降低可靠性。

刻意只由 web 入口（wsgi.py）呼叫 `start_embedded_worker()`，**不放進 create_app()**——
否則 `manage.py`（init-db／run-worker／seed-demo）與 pytest 都會被 create_app() 連帶啟動
一個背景 worker（run-worker 會變雙 worker、測試會有背景執行緒亂寫 in-memory DB）。
"""
from __future__ import annotations

import asyncio
import atexit
import logging
import os
import socket
import threading

from flask import Flask

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_worker_process = None  # app.jobs.process.WorkerProcess（延後 import 避免循環）


def _disabled() -> bool:
    return os.environ.get("V2PLUS_EMBEDDED_WORKER", "true").strip().lower() in (
        "0", "false", "no", "off",
    )


def start_embedded_worker(app: Flask) -> bool:
    """在 daemon thread 啟動 WorkerProcess.run_forever()。已啟動或不該啟動時回傳 False。

    回傳值：True＝本次確實啟動了背景執行緒；False＝略過（測試／停用／未設 factory／已在跑）。
    """
    global _worker_thread, _worker_process

    if app.config.get("TESTING"):
        return False
    if _disabled():
        logger.info("embedded_worker_disabled（V2PLUS_EMBEDDED_WORKER=false）")
        return False

    factory_path = os.environ.get("V2PLUS_GRAPH_CLIENT_FACTORY", "").strip()
    if not factory_path:
        logger.warning(
            "embedded_worker_not_started：未設定 V2PLUS_GRAPH_CLIENT_FACTORY，"
            "同步工作會停在佇列；設好後重啟 web，或改用 manage.py run-worker。"
        )
        return False

    with _lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return False  # 同一 process 內已啟動，避免重複

        def _run() -> None:
            global _worker_process
            from app.extensions import db
            from app.jobs.bootstrap import build_handlers, load_graph_client_factory
            from app.jobs.process import WorkerProcess
            from app.jobs.worker import WorkerMetrics, WorkerRunner

            with app.app_context():
                try:
                    graph_client_factory = load_graph_client_factory(factory_path)
                except Exception:  # noqa: BLE001 — factory 載入失敗不可拖垮 web
                    logger.exception("embedded_worker_factory_load_failed")
                    return
                worker_id = f"embedded-{socket.gethostname()}-{os.getpid()}"
                runner = WorkerRunner(
                    db.session,
                    build_handlers(db.session, graph_client_factory),
                    worker_id=worker_id,
                    metrics=WorkerMetrics(),
                )
                _worker_process = WorkerProcess(db.session, runner, poll_seconds=2.0)
                logger.info("embedded_worker_started worker_id=%s", worker_id)
                try:
                    asyncio.run(_worker_process.run_forever())
                except Exception:  # noqa: BLE001
                    logger.exception("embedded_worker_crashed")
                finally:
                    db.session.remove()

        _worker_thread = threading.Thread(
            target=_run, name="v2plus-embedded-worker", daemon=True,
        )
        _worker_thread.start()

    atexit.register(_request_stop)
    return True


def _request_stop() -> None:
    if _worker_process is not None:
        _worker_process.request_stop()
