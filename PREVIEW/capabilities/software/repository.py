from app.capabilities.software.models import DetectedSoftware
from app.storage.repository import TenantScopedRepository
class SoftwareRepository(TenantScopedRepository):
    model = DetectedSoftware
    def list_rows(self): return self._base_query().order_by(DetectedSoftware.device_count.desc(), DetectedSoftware.display_name).all()
