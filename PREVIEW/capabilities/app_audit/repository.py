from app.capabilities.app_audit.models import AppRegistration, EnterpriseApp
from app.storage.repository import TenantScopedRepository

class AppRegistrationRepository(TenantScopedRepository):
    model = AppRegistration
    def list_rows(self): return self._base_query().order_by(AppRegistration.display_name).all()

class EnterpriseAppRepository(TenantScopedRepository):
    model = EnterpriseApp
    def list_rows(self): return self._base_query().order_by(EnterpriseApp.display_name).all()
