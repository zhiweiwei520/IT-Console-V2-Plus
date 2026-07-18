from app.capabilities.defender.models import DefenderAlert
from app.storage.repository import TenantScopedRepository
DEFAULT_LIST_LIMIT=200
class DefenderRepository(TenantScopedRepository):
    model=DefenderAlert
    def list_recent(self,limit=DEFAULT_LIST_LIMIT): return self._base_query().order_by(DefenderAlert.created_datetime.desc()).limit(limit).all()
