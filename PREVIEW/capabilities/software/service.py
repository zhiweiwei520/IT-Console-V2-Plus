from sqlalchemy import delete, or_, select
from app.capabilities.software.models import DetectedSoftware
from app.capabilities.software.repository import SoftwareRepository
class SoftwareService:
    def __init__(self, session, context): self.context, self.repository = context, SoftwareRepository(session, context)
    def list_rows(self):
        if not self.context.has_permission("software.view"): raise PermissionError("software.view required")
        return self.repository.list_rows()
class SoftwareSyncService:
    def __init__(self, session, *, environment_id, managed_tenant_id, sync_id): self.session, self.environment_id, self.managed_tenant_id, self.sync_id = session, environment_id, managed_tenant_id, sync_id
    def upsert(self, values):
        for raw in values:
            source, name = str(raw.get("id") or "").strip(), str(raw.get("displayName") or "").strip()
            if not source or not name: raise ValueError("detected app missing id or displayName")
            row = self.session.execute(select(DetectedSoftware).where(DetectedSoftware.environment_id == self.environment_id, DetectedSoftware.managed_tenant_id == self.managed_tenant_id, DetectedSoftware.source_object_id == source)).scalar_one_or_none()
            if row is None: row = DetectedSoftware(environment_id=self.environment_id, managed_tenant_id=self.managed_tenant_id, source_object_id=source); self.session.add(row)
            row.display_name, row.version, row.publisher, row.platform = name, raw.get("version"), raw.get("publisher"), raw.get("platform")
            row.size_in_bytes, row.device_count, row.last_seen_sync_id = raw.get("sizeInByte"), int(raw.get("deviceCount") or 0), self.sync_id
        return len(values)
    def finalize(self): self.session.execute(delete(DetectedSoftware).where(DetectedSoftware.environment_id == self.environment_id, DetectedSoftware.managed_tenant_id == self.managed_tenant_id, or_(DetectedSoftware.last_seen_sync_id.is_(None), DetectedSoftware.last_seen_sync_id != self.sync_id)))
