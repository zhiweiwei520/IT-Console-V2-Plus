from app.capabilities.sharepoint.models import SharePointSiteAudit
from app.storage.repository import TenantScopedRepository
class SharePointRepository(TenantScopedRepository):
    model=SharePointSiteAudit
    def list_rows(self): return self._base_query().order_by(SharePointSiteAudit.display_name).all()
