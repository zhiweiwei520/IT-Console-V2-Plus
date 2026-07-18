import uuid
from urllib.parse import urlparse
from sqlalchemy import select
from app.capabilities.app_audit.models import AppAuditCheckpoint
from app.capabilities.app_audit.service import AppAuditSyncService
from app.jobs.worker import RetryableJobError, TerminalJobError
from app.microsoft.graph_client import GraphRetryableError, GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive

class AppAuditSyncHandler:
    def __init__(self, session, graph_client_factory): self.session, self.graph_client_factory = session, graph_client_factory
    async def handle(self, envelope, *, queue, worker_id, lease_seconds):
        job_id, env_id, tenant_id = map(uuid.UUID, (envelope["message_id"], envelope["environment_id"], envelope["managed_tenant_id"]))
        cp = self.session.execute(select(AppAuditCheckpoint).where(AppAuditCheckpoint.job_id == job_id)).scalar_one_or_none()
        if cp and cp.status == "completed": return
        if cp is None: cp = AppAuditCheckpoint(job_id=job_id, environment_id=env_id, managed_tenant_id=tenant_id, phase="applications", next_resource="/applications"); self.session.add(cp); self.session.flush()
        client, service = self.graph_client_factory(env_id, tenant_id), AppAuditSyncService(self.session, environment_id=env_id, managed_tenant_id=tenant_id, sync_id=job_id)
        while cp.next_resource:
            self._validate(cp.next_resource)
            try: response = await client.get(cp.next_resource, params={"$select": "id,appId,displayName,signInAudience,publisherDomain,passwordCredentials,keyCredentials"} if cp.next_resource == "/applications" else ({"$select": "id,appId,displayName,accountEnabled,servicePrincipalType,appOwnerOrganizationId"} if cp.next_resource == "/servicePrincipals" else None))
            except GraphRetryableError as exc: raise RetryableJobError(exc.code, delay_seconds=exc.retry_after) from exc
            except GraphTerminalError as exc:
                if exc.code == "graph_authorization_failed":
                    connection = self.session.execute(select(TenantConnection).where(TenantConnection.managed_tenant_id == tenant_id)).scalar_one_or_none()
                    if connection and connection.status == "active": connection.status = "degraded"; connection.updated_at = utc_now_naive(); self.session.commit()
                raise TerminalJobError(exc.code) from exc
            except Exception as exc: raise RetryableJobError("graph_request_failed", delay_seconds=30) from exc
            values, next_link = response.get("value"), response.get("@odata.nextLink")
            if not isinstance(values, list): raise TerminalJobError("graph_response_invalid")
            if next_link is not None and not isinstance(next_link, str): raise TerminalJobError("graph_next_link_invalid")
            try: cp.processed_count += service.upsert(cp.phase, values)
            except ValueError as exc: raise TerminalJobError("graph_app_audit_invalid") from exc
            if next_link: cp.next_resource = next_link
            elif cp.phase == "applications": cp.phase, cp.next_resource = "service_principals", "/servicePrincipals"
            else: cp.next_resource = None
            cp.updated_at = utc_now_naive(); queue.heartbeat(envelope["message_id"], worker_id=worker_id, lease_seconds=lease_seconds); self.session.commit()
        service.finalize(); cp.status = "completed"; cp.completed_at = utc_now_naive(); cp.updated_at = cp.completed_at; self.session.commit()
    @staticmethod
    def _validate(resource):
        p = urlparse(resource)
        if not resource.startswith("/") and (p.scheme != "https" or p.netloc.lower() != "graph.microsoft.com"): raise TerminalJobError("graph_next_link_not_allowed")
