from __future__ import annotations

from app.capabilities.devices.models import Device
from app.storage.repository import TenantScopedRepository


class DeviceRepository(TenantScopedRepository):
    model = Device

    def list_devices(self):
        return self._base_query().order_by(Device.device_name.asc()).all()
