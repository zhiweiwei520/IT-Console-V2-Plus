from app.capabilities.sentinel.models import SecurityIncident
from app.storage.repository import TenantScopedRepository
DEFAULT_LIST_LIMIT=200
class SentinelRepository(TenantScopedRepository):
    model=SecurityIncident
    def list_recent(self,limit=DEFAULT_LIST_LIMIT): return self._base_query().order_by(SecurityIncident.created_datetime.desc()).limit(limit).all()
