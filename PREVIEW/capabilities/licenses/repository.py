from app.capabilities.licenses.models import LicenseSku, MfaRegistration
from app.storage.repository import TenantScopedRepository


class LicenseSkuRepository(TenantScopedRepository):
    model = LicenseSku
    def list_skus(self):
        return self._base_query().order_by(LicenseSku.sku_part_number).all()


class MfaRegistrationRepository(TenantScopedRepository):
    model = MfaRegistration
    def list_users(self):
        return self._base_query().order_by(MfaRegistration.user_principal_name).all()
