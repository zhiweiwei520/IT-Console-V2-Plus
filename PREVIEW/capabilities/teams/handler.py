import uuid
from urllib.parse import urlparse
from sqlalchemy import select
from app.capabilities.teams.models import TeamsSyncCheckpoint
from app.capabilities.teams.service import TeamsSyncService
from app.jobs.worker import RetryableJobError,TerminalJobError
from app.microsoft.graph_client import GraphRetryableError,GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive
class TeamsSyncHandler:
    def __init__(self,session,graph_client_factory): self.session,self.graph_client_factory=session,graph_client_factory
    async def handle(self,envelope,*,queue,worker_id,lease_seconds):
        job_id,env_id,tenant_id=map(uuid.UUID,(envelope["message_id"],envelope["environment_id"],envelope["managed_tenant_id"]))
        cp=self.session.execute(select(TeamsSyncCheckpoint).where(TeamsSyncCheckpoint.job_id==job_id)).scalar_one_or_none()
        if cp and cp.status=="completed": return
        if cp is None: cp=TeamsSyncCheckpoint(job_id=job_id,environment_id=env_id,managed_tenant_id=tenant_id,next_resource="/groups"); self.session.add(cp); self.session.flush()
        client,service=self.graph_client_factory(env_id,tenant_id),TeamsSyncService(self.session,environment_id=env_id,managed_tenant_id=tenant_id,sync_id=job_id)
        while cp.next_resource:
            try:
                response=await client.get(cp.next_resource,params={"$filter":"resourceProvisioningOptions/Any(x:x eq 'Team')","$select":"id,displayName,description,visibility,classification,createdDateTime,resourceProvisioningOptions"} if cp.next_resource=="/groups" else None)
                groups=response.get("value"); next_link=response.get("@odata.nextLink")
                if not isinstance(groups,list): raise TerminalJobError("graph_response_invalid")
                if next_link is not None and not isinstance(next_link,str): raise TerminalJobError("graph_next_link_invalid")
                for group in groups:
                    team_id=str(group.get("id") or ""); team=await client.get(f"/teams/{team_id}")
                    group["isArchived"]=team.get("isArchived",False)
                    channels=(await client.get(f"/teams/{team_id}/channels")).get("value",[])
                    members=(await client.get(f"/groups/{team_id}/members",params={"$select":"id,displayName,userPrincipalName,userType"})).get("value",[])
                    owners=(await client.get(f"/groups/{team_id}/owners",params={"$select":"id,displayName,userPrincipalName"})).get("value",[])
                    apps=(await client.get(f"/teams/{team_id}/installedApps",params={"$expand":"teamsAppDefinition"})).get("value",[])
                    if not all(isinstance(x,list) for x in (channels,members,owners,apps)): raise TerminalJobError("graph_team_detail_invalid")
                    service.upsert(group,channels=channels,members=members,owners=owners,apps=apps); cp.processed_count+=1
            except GraphRetryableError as exc: raise RetryableJobError(exc.code,delay_seconds=exc.retry_after) from exc
            except GraphTerminalError as exc:
                if exc.code=="graph_authorization_failed":
                    connection=self.session.execute(select(TenantConnection).where(TenantConnection.managed_tenant_id==tenant_id)).scalar_one_or_none()
                    if connection and connection.status=="active": connection.status="degraded"; connection.updated_at=utc_now_naive(); self.session.commit()
                raise TerminalJobError(exc.code) from exc
            except (RetryableJobError,TerminalJobError): raise
            except ValueError as exc: raise TerminalJobError("graph_team_invalid") from exc
            except Exception as exc: raise RetryableJobError("graph_request_failed",delay_seconds=30) from exc
            cp.next_resource=next_link; cp.updated_at=utc_now_naive(); queue.heartbeat(envelope["message_id"],worker_id=worker_id,lease_seconds=lease_seconds); self.session.commit()
        service.finalize(); cp.status="completed"; cp.completed_at=utc_now_naive(); cp.updated_at=cp.completed_at; self.session.commit()
