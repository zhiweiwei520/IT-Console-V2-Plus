from app.capabilities.teams.models import TeamAudit
from app.storage.repository import TenantScopedRepository
class TeamsRepository(TenantScopedRepository):
    model=TeamAudit
    def list_rows(self): return self._base_query().order_by(TeamAudit.display_name).all()
