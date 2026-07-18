from sqlalchemy import delete, or_, select
from app.capabilities.app_audit.models import AppRegistration, EnterpriseApp
from app.capabilities.app_audit.repository import AppRegistrationRepository, EnterpriseAppRepository

class AppAuditService:
    def __init__(self, session, context): self.context, self.apps, self.enterprise = context, AppRegistrationRepository(session, context), EnterpriseAppRepository(session, context)
    def list_results(self):
        if not self.context.has_permission("app_audit.view"): raise PermissionError("app_audit.view required")
        return self.apps.list_rows(), self.enterprise.list_rows()

class AppAuditSyncService:
    def __init__(self, session, *, environment_id, managed_tenant_id, sync_id): self.session, self.environment_id, self.managed_tenant_id, self.sync_id = session, environment_id, managed_tenant_id, sync_id
    def upsert(self, phase, values):
        model = AppRegistration if phase == "applications" else EnterpriseApp
        for raw in values:
            source, app_id, name = (str(raw.get(k) or "").strip() for k in ("id", "appId", "displayName"))
            if not source or not app_id or not name: raise ValueError("app audit row missing id, appId or displayName")
            row = self.session.execute(select(model).where(model.environment_id == self.environment_id, model.managed_tenant_id == self.managed_tenant_id, model.source_object_id == source)).scalar_one_or_none()
            if row is None: row = model(environment_id=self.environment_id, managed_tenant_id=self.managed_tenant_id, source_object_id=source); self.session.add(row)
            row.app_id, row.display_name, row.last_seen_sync_id = app_id, name, self.sync_id
            if phase == "applications":
                row.sign_in_audience, row.publisher_domain = raw.get("signInAudience"), raw.get("publisherDomain")
                credentials = list(raw.get("passwordCredentials") or []) + list(raw.get("keyCredentials") or [])
                expiries = sorted(str(x.get("endDateTime")) for x in credentials if x.get("endDateTime"))
                row.credential_count, row.nearest_credential_expiry = len(credentials), (expiries[0] if expiries else None)
            else:
                row.account_enabled, row.service_principal_type, row.app_owner_organization_id = raw.get("accountEnabled"), raw.get("servicePrincipalType"), raw.get("appOwnerOrganizationId")
        return len(values)
    def finalize(self):
        for model in (AppRegistration, EnterpriseApp): self.session.execute(delete(model).where(model.environment_id == self.environment_id, model.managed_tenant_id == self.managed_tenant_id, or_(model.last_seen_sync_id.is_(None), model.last_seen_sync_id != self.sync_id)))
