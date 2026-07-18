import uuid
from datetime import timedelta
from urllib.parse import urlparse
from sqlalchemy import select
from app.capabilities.defender.models import DefenderSyncCheckpoint
from app.capabilities.defender.service import DefenderSyncService,to_graph_filter_iso
from app.jobs.worker import RetryableJobError,TerminalJobError
from app.microsoft.graph_client import GraphRetryableError,GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive
_ALERTS="/security/alerts_v2"
_SELECT="id,title,category,severity,status,createdDateTime,lastUpdateDateTime,serviceSource,detectionSource,description,alertWebUrl"
_PAGE_SIZE=200
_INITIAL_WINDOW_DAYS=30
class DefenderSyncHandler:
    def __init__(self,session,graph_client_factory): self.session,self.graph_client_factory=session,graph_client_factory
    async def handle(self,envelope,*,queue,worker_id,lease_seconds):
        job_id,env_id,tenant_id=map(uuid.UUID,(envelope["message_id"],envelope["environment_id"],envelope["managed_tenant_id"]))
        service=DefenderSyncService(self.session,environment_id=env_id,managed_tenant_id=tenant_id,sync_id=job_id)
        cp=self.session.execute(select(DefenderSyncCheckpoint).where(DefenderSyncCheckpoint.job_id==job_id)).scalar_one_or_none()
        if cp and cp.status=="completed": return
        if cp is None:
            # watermark 只在此算一次並釘進 window_start；resume 沿用不重算（避免跨頁邊界漂移，見 signin_logs）。
            watermark=service.watermark() or (utc_now_naive()-timedelta(days=_INITIAL_WINDOW_DAYS))
            cp=DefenderSyncCheckpoint(job_id=job_id,environment_id=env_id,managed_tenant_id=tenant_id,window_start=to_graph_filter_iso(watermark),next_resource=_ALERTS); self.session.add(cp); self.session.flush()
        client=self.graph_client_factory(env_id,tenant_id)
        while cp.next_resource:
            self._validate(cp.next_resource)
            try: response=await client.get(cp.next_resource,params=self._params(cp.window_start) if cp.next_resource==_ALERTS else None)
            except GraphRetryableError as exc: raise RetryableJobError(exc.code,delay_seconds=exc.retry_after) from exc
            except GraphTerminalError as exc:
                if exc.code=="graph_authorization_failed":
                    connection=self.session.execute(select(TenantConnection).where(TenantConnection.managed_tenant_id==tenant_id)).scalar_one_or_none()
                    if connection and connection.status=="active": connection.status="degraded"; connection.updated_at=utc_now_naive(); self.session.commit()
                raise TerminalJobError(exc.code) from exc
            except (RetryableJobError,TerminalJobError): raise
            except Exception as exc: raise RetryableJobError("graph_request_failed",delay_seconds=30) from exc
            alerts,next_link=response.get("value"),response.get("@odata.nextLink")
            if not isinstance(alerts,list): raise TerminalJobError("graph_response_invalid")
            if next_link is not None and not isinstance(next_link,str): raise TerminalJobError("graph_next_link_invalid")
            try: cp.processed_count+=service.upsert_page(alerts)
            except ValueError as exc: raise TerminalJobError("graph_alert_invalid") from exc
            cp.next_resource=next_link; cp.updated_at=utc_now_naive(); queue.heartbeat(envelope["message_id"],worker_id=worker_id,lease_seconds=lease_seconds); self.session.commit()
        # append-only：完成即結束，不做刪除 finalize。
        cp.status="completed"; cp.completed_at=utc_now_naive(); cp.updated_at=cp.completed_at; self.session.commit()
    @staticmethod
    def _params(window_start):
        params={"$orderby":"createdDateTime","$top":_PAGE_SIZE,"$select":_SELECT}
        # `ge`（>=）而非 `gt`：搭配 (tenant, id) 冪等 upsert，邊界同秒告警重抓也不漏不重。
        if window_start: params["$filter"]=f"createdDateTime ge {window_start}"
        return params
    @staticmethod
    def _validate(resource):
        p=urlparse(resource)
        if not resource.startswith("/") and (p.scheme!="https" or p.netloc.lower()!="graph.microsoft.com"): raise TerminalJobError("graph_next_link_not_allowed")
