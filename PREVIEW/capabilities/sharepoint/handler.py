import uuid
from sqlalchemy import select
from app.capabilities.sharepoint.models import SharePointSyncCheckpoint
from app.capabilities.sharepoint.service import SharePointSyncService
from app.jobs.worker import RetryableJobError,TerminalJobError
from app.microsoft.graph_client import GraphRetryableError,GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive
class SharePointSyncHandler:
    def __init__(self,session,graph_client_factory): self.session,self.graph_client_factory=session,graph_client_factory
    async def handle(self,envelope,*,queue,worker_id,lease_seconds):
        job_id,env_id,tenant_id=map(uuid.UUID,(envelope["message_id"],envelope["environment_id"],envelope["managed_tenant_id"]))
        cp=self.session.execute(select(SharePointSyncCheckpoint).where(SharePointSyncCheckpoint.job_id==job_id)).scalar_one_or_none()
        if cp and cp.status=="completed": return
        if cp is None: cp=SharePointSyncCheckpoint(job_id=job_id,environment_id=env_id,managed_tenant_id=tenant_id,next_resource="/sites"); self.session.add(cp); self.session.flush()
        client,service=self.graph_client_factory(env_id,tenant_id),SharePointSyncService(self.session,environment_id=env_id,managed_tenant_id=tenant_id,sync_id=job_id)
        while cp.next_resource:
            try:
                response=await client.get(cp.next_resource,params={"search":"*","$select":"id,name,displayName,webUrl,description,createdDateTime,lastModifiedDateTime,siteCollection"} if cp.next_resource=="/sites" else None)
                sites=response.get("value"); next_link=response.get("@odata.nextLink")
                if not isinstance(sites,list): raise TerminalJobError("graph_response_invalid")
                if next_link is not None and not isinstance(next_link,str): raise TerminalJobError("graph_next_link_invalid")
                for site in sites:
                    site_id=str(site.get("id") or "")
                    drives=(await client.get(f"/sites/{site_id}/drives",params={"$select":"id,name,driveType,quota"})).get("value",[])
                    if not isinstance(drives,list): raise TerminalJobError("graph_site_detail_invalid")
                    service.upsert(site,drives=drives); cp.processed_count+=1
            except GraphRetryableError as exc: raise RetryableJobError(exc.code,delay_seconds=exc.retry_after) from exc
            except GraphTerminalError as exc:
                if exc.code=="graph_authorization_failed":
                    connection=self.session.execute(select(TenantConnection).where(TenantConnection.managed_tenant_id==tenant_id)).scalar_one_or_none()
                    if connection and connection.status=="active": connection.status="degraded"; connection.updated_at=utc_now_naive(); self.session.commit()
                raise TerminalJobError(exc.code) from exc
            except (RetryableJobError,TerminalJobError): raise
            except ValueError as exc: raise TerminalJobError("graph_site_invalid") from exc
            except Exception as exc: raise RetryableJobError("graph_request_failed",delay_seconds=30) from exc
            cp.next_resource=next_link; cp.updated_at=utc_now_naive(); queue.heartbeat(envelope["message_id"],worker_id=worker_id,lease_seconds=lease_seconds); self.session.commit()
        service.finalize(); cp.status="completed"; cp.completed_at=utc_now_naive(); cp.updated_at=cp.completed_at; self.session.commit()
