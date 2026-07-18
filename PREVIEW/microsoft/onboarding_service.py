"""
Managed Tenant 連接（BYO app 自助輸入版）。

04-microsoft-connection-and-consent.md §4 描述的是 Admin Consent 互動導轉流程（需要
Provider App bundle 與真實 Entra Tenant 才能測試，本 spike 尚未取得，見 capability-manifest）。
這裡實作的是同一份文件 §2 列的另一條路：「Customer BYO app：客戶在自己 Tenant 建 App，
V2+ 保存 credential reference」——不需要導轉去 Microsoft，環境管理者自己在 Entra 建好
App Registration 後，把 tenant id／client id／client secret 貼進表單即可，可用真實
Entra Tenant 端到端測試。

「測試連線」呼叫 Graph `/organization` 對照 04 §4 步驟 5「以 organization／service principal
查詢確認實際 Tenant」，並比對使用者輸入的 entra_tenant_id 與回傳值是否一致，防止
client_id/secret 屬於錯誤 Tenant 卻被誤判為成功連線。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.extensions import db
from app.microsoft.encryption import encrypt_secret
from app.microsoft.factory import GraphClientFactoryError, default_graph_client_factory
from app.microsoft.graph_client import GraphRetryableError, GraphTerminalError
from app.microsoft.models import ManagedTenant, TenantConnection
from app.microsoft.token_broker import TokenAcquisitionError


def create_byo_managed_tenant(
    environment_id,
    *,
    entra_tenant_id: str,
    display_name: str,
    domain: str | None,
    client_id: str,
    client_secret: str,
) -> ManagedTenant:
    entra_tenant_id = (entra_tenant_id or "").strip()
    display_name = (display_name or "").strip()
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    domain = (domain or "").strip() or None

    if not display_name:
        raise ValueError("顯示名稱不可為空")
    if not client_id or not client_secret:
        raise ValueError("BYO app 需要同時提供 client_id 與 client_secret")
    try:
        uuid.UUID(entra_tenant_id)
    except ValueError as exc:
        raise ValueError("Entra Tenant ID 必須是有效的 GUID") from exc

    if ManagedTenant.query.filter_by(
        environment_id=environment_id, entra_tenant_id=entra_tenant_id,
    ).first() is not None:
        raise ValueError("此 Entra Tenant 已存在於這個環境")

    tenant = ManagedTenant(
        environment_id=environment_id, entra_tenant_id=entra_tenant_id,
        display_name=display_name, domain=domain, status="pending",
    )
    db.session.add(tenant)
    db.session.flush()

    connection = TenantConnection(
        environment_id=environment_id, managed_tenant_id=tenant.id,
        auth_mode="byo_app", client_id=client_id, status="pending",
    )
    db.session.add(connection)
    db.session.flush()
    connection.encrypted_client_secret = encrypt_secret(client_secret)
    connection.credential_ref = f"db:{connection.id}"
    db.session.commit()
    return tenant


@dataclass(frozen=True)
class ConnectionTestResult:
    success: bool
    error: str | None = None
    remote_tenant_id: str | None = None
    remote_display_name: str | None = None


async def test_tenant_connection(environment_id, managed_tenant_id) -> ConnectionTestResult:
    try:
        client = default_graph_client_factory(environment_id, managed_tenant_id, include_pending=True)
        response = await client.get("/organization")
    except GraphClientFactoryError as exc:
        return ConnectionTestResult(success=False, error=f"連線設定不可用：{exc}")
    except TokenAcquisitionError as exc:
        return ConnectionTestResult(success=False, error=f"無法取得 token：{exc.code}")
    except GraphTerminalError as exc:
        return ConnectionTestResult(success=False, error=f"Graph 拒絕請求：{exc.code}")
    except GraphRetryableError as exc:
        return ConnectionTestResult(success=False, error=f"Graph 暫時無法連線（{exc.code}），請稍後重試")
    except Exception as exc:  # noqa: BLE001 — 使用者觸發的「測試連線」動作不可 500，最後防線
        return ConnectionTestResult(success=False, error=f"未預期的錯誤：{exc}")

    orgs = response.get("value") if isinstance(response, dict) else None
    if not orgs:
        return ConnectionTestResult(success=False, error="/organization 回傳空結果")
    remote_id = orgs[0].get("id")
    remote_name = orgs[0].get("displayName")
    return ConnectionTestResult(success=True, remote_tenant_id=remote_id, remote_display_name=remote_name)


def apply_connection_test_result(
    tenant: ManagedTenant, connection: TenantConnection, result: ConnectionTestResult,
) -> None:
    """把測試結果落地為狀態變更；呼叫端負責 commit。"""
    if not result.success:
        connection.status = "degraded" if connection.status == "active" else "pending"
        tenant.status = "degraded" if tenant.status == "active" else "pending"
        return

    if result.remote_tenant_id and result.remote_tenant_id != tenant.entra_tenant_id:
        connection.status = "pending"
        tenant.status = "pending"
        raise ValueError(
            f"回傳的 Tenant ID（{result.remote_tenant_id}）與輸入值（{tenant.entra_tenant_id}）不符，"
            "請確認 client_id／client_secret 屬於正確的 Entra Tenant"
        )

    connection.status = "active"
    tenant.status = "active"
    if result.remote_display_name and tenant.display_name != result.remote_display_name:
        tenant.display_name = result.remote_display_name
