from sqlalchemy import delete, or_, select

from app.capabilities.licenses.models import LicenseSku, MfaRegistration
from app.capabilities.licenses.repository import LicenseSkuRepository, MfaRegistrationRepository


class LicenseAuditService:
    def __init__(self, session, context):
        self.context = context
        self.skus = LicenseSkuRepository(session, context)
        self.mfa = MfaRegistrationRepository(session, context)

    def list_results(self):
        if not self.context.has_permission("licenses.view"):
            raise PermissionError("licenses.view required")
        return self.skus.list_skus(), self.mfa.list_users()


class LicenseAuditSyncService:
    def __init__(self, session, *, environment_id, managed_tenant_id, sync_id):
        self.session, self.environment_id, self.managed_tenant_id, self.sync_id = session, environment_id, managed_tenant_id, sync_id

    def upsert_licenses(self, values):
        for raw in values:
            source_id = str(raw.get("skuId") or raw.get("id") or "").strip()
            part = str(raw.get("skuPartNumber") or "").strip()
            if not source_id or not part:
                raise ValueError("subscribedSku missing skuId or skuPartNumber")
            row = self._row(LicenseSku, source_id)
            prepaid = raw.get("prepaidUnits") or {}
            row.sku_part_number, row.capability_status = part, raw.get("capabilityStatus")
            row.enabled_units = int(prepaid.get("enabled") or 0)
            row.warning_units = int(prepaid.get("warning") or 0)
            row.suspended_units = int(prepaid.get("suspended") or 0)
            row.consumed_units = int(raw.get("consumedUnits") or 0)
            row.last_seen_sync_id = self.sync_id
        return len(values)

    def upsert_mfa(self, values):
        for raw in values:
            source_id = str(raw.get("id") or "").strip()
            upn = str(raw.get("userPrincipalName") or "").strip()
            if not source_id or not upn:
                raise ValueError("MFA registration missing id or userPrincipalName")
            row = self._row(MfaRegistration, source_id)
            row.user_principal_name = upn
            row.user_display_name = str(raw.get("userDisplayName") or "").strip() or None
            row.is_mfa_registered = bool(raw.get("isMfaRegistered"))
            row.is_mfa_capable = bool(raw.get("isMfaCapable"))
            methods = raw.get("methodsRegistered") or []
            row.methods_registered = ", ".join(str(x) for x in methods) if isinstance(methods, list) else None
            row.last_seen_sync_id = self.sync_id
        return len(values)

    def _row(self, model, source_id):
        row = self.session.execute(select(model).where(model.environment_id == self.environment_id, model.managed_tenant_id == self.managed_tenant_id, model.source_object_id == source_id)).scalar_one_or_none()
        if row is None:
            row = model(environment_id=self.environment_id, managed_tenant_id=self.managed_tenant_id, source_object_id=source_id)
            self.session.add(row)
        return row

    def finalize(self):
        for model in (LicenseSku, MfaRegistration):
            self.session.execute(delete(model).where(
                model.environment_id == self.environment_id,
                model.managed_tenant_id == self.managed_tenant_id,
                or_(model.last_seen_sync_id.is_(None), model.last_seen_sync_id != self.sync_id),
            ))
