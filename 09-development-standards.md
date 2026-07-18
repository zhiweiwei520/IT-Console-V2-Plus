# 09 — V2+ 開發規約

本文件補充根目錄 `AGENTS.md`；衝突時仍以專案根規範與已核准 ADR 為準。

## 1. Package 邊界

建議逐步整理為：

```text
app/
  platform/        # Principal、Environment、Membership、RBAC、audit
  control_plane/   # catalog、plan、placement、provisioning
  microsoft/       # connection、consent、token、Graph client
  capabilities/    # accounts、intune、teams、sharepoint、security...
  jobs/            # definitions、dispatcher、handlers、outbox
  storage/         # scoped repository、RLS context、Blob abstraction
  web/             # blueprint、DTO、forms
```

不要求一次搬完目錄。先以介面切斷全域設定依賴，再在 feature 修改時漸進搬移。

## 2. TenantContext 規則

- 任何客戶資料的 route、service、repository、Worker handler 都必須顯式接收 `TenantContext`。
- 禁止從 module global、form、query string 或任意 header 自行取得 Environment。
- Web 業務模組的 `managed_tenant_id` 只允許取自已驗證的 server-side session；form、query string 與任意 header 不得切換或覆寫目前 Tenant。
- 帳號、裝置、登入記錄及後續所有 Managed Tenant 資料模組必須要求單一 `active_managed_tenant_id`；未選擇時導向 Tenant 選擇頁，不得退回 Environment 全量查詢。
- 切換 Environment、登出、membership version 失效或 Tenant 狀態失效時，必須清除 session 內目前 Tenant。
- Repository 方法不得提供無 scope 的 `all()`／`get(id)`；使用 `list_for_environment()`、`get_authorized()` 等明確介面。
- 跨 Tenant 聚合需獨立 method 並驗證完整 grants，不以 `managed_tenant_id=None` 表示「全部」。
- Background message scope 必須回 DB 重新驗證，不因訊息來自 Service Bus 就信任。
- 無 context 或 environment／tenant 不符時 fail-closed。

選單沿用 IT Console V2 左側階層式 sidebar；功能入口依 permission OR gating，Tenant 選擇／設定為 Environment 層入口，Tenant 業務功能歸在「查詢功能 → M365」。新增模組不得另做頂部平鋪導覽或頁內 Tenant 下拉選擇器。

## 3. ID 與約束

- V2+ 新領域主鍵使用 UUID；外部 Graph ID 只作 `source_object_id`，不作跨 Tenant 主鍵。
- 所有 Microsoft 資料 unique 至少含 `managed_tenant_id`。
- 所有 Environment 子資料 FK／unique／index 含 `environment_id`；能用複合 FK 防跨界關聯時必須使用。
- URL 使用內部 UUID，不直接使用 Entra Tenant ID、UPN 或可推測自然鍵。
- Email／UPN 可變，不作永久授權識別；使用 issuer + immutable subject。
- Entra external login 固定使用 `(canonical_issuer, subject)`；`tid/oid/home_account_id` 是稽核與 linking attributes，禁止以 email／UPN fallback 綁定。

## 4. 設定與秘密

設定覆寫順序：

```text
platform default -> plan/stamp -> environment -> managed tenant -> job target
```

- 每層只允許 schema 已登錄的 key，禁止任意 JSON key 靜默生效。
- 非機密設定可進 DB／App Configuration；secret 只能保存 Key Vault reference。
- 所有 setting 讀取 API 都要求 scope；禁止新增全域 `get_system_settings()` 呼叫。
- Endpoint、authority、cloud 走 enum／allowlist，不接受任意 URL。

## 5. API 規約

- JSON API 以 `/api/v2/...` 版本化；SSR route 可維持人類可讀路徑。
- List 預設分頁、穩定排序與上限；高成本 filter 由 server 驗證。
- 建立長工作回 `202 Accepted` + `operation_id`／`batch_id`，不阻塞 request。
- Error 使用穩定 machine code、correlation ID 與安全訊息；不回傳 upstream raw error／token。
- 跨 Environment object 對一般使用者回 404；已知物件但權限不足的同環境操作可回 403。
- 寫入、匯出、同步、下載仍使用窄 permission；UI 隱藏不能取代後端授權。

## 6. Queue 訊息契約

訊息 envelope：

```json
{
  "schema_version": 1,
  "message_id": "uuid",
  "environment_id": "uuid",
  "managed_tenant_id": "uuid",
  "execution_id": "uuid",
  "job_type": "teams.sync",
  "job_version": 1,
  "attempt": 1,
  "trace_id": "w3c-trace-id",
  "requested_at": "UTC ISO-8601"
}
```

- 不放 secret、access token、完整設定、Graph response 或使用者檔案。
- Handler 先查 execution 與 scope，再取得 connection／credential。
- Handler 必須分別宣告：排程 occurrence key（job definition + target + scheduled time + version）、人工 operation UUID、message／step idempotency key（tenant execution + step + checkpoint）、retryable error、terminal error 與 compensation 行為。
- 訊息 schema 只做向後相容擴充；破壞性變更需新 version 與雙版本消費窗口。

## 7. Database migration

- Schema 只由 Alembic 管理；production 禁止 `db.create_all()` 與 runtime `ensure_*_schema()`。
- 採 expand／migrate／contract；大型 backfill 以可重跑 job 執行，不在 DDL transaction 一次掃全表。
- 新 pooled table 必附 RLS migration、policy、index、repository test 與負向隔離 test。
- Migration job 使用專用 identity／role；Web／Worker app role 不可 DDL。
- 時間一律儲存 UTC；若延續 naive UTC，須保持現行 helper 規範並在 schema 文件標示。

## 8. Graph client

- Capability service 只依賴 `GraphClient` protocol，不自行 new MSAL client 或讀 credential。
- 所有呼叫記錄 resource、status、duration、request-id；敏感 query／body redacted。
- 分頁、batch、delta、Retry-After、backoff、circuit breaker 集中在共用 client。
- 單 Tenant concurrency 由 shared limiter 控制；不得在 capability 內建立無界 ThreadPool。
- Graph beta endpoint 預設禁止；若必須使用，需 ADR、feature flag、contract test 與退場策略。

## 9. Audit 與資料最小化

- 每個狀態改變需 audit：actor、environment、managed tenant、action、target、outcome、reason、correlation ID。
- 高風險 DB mutation 與 audit／outbox 必須同 transaction；外部 side effect 先保存 durable intent，再由 Worker 寫 outcome audit。
- 不記 password、token、secret、certificate private key、OAuth code、完整 delta link。
- Graph raw payload 只保存功能所需欄位；新增欄位前定義 retention 與顯示授權。
- 匯出欄位標示 UTC+8 的現行規範若仍適用則沿用；全球 SaaS 決策後改由 Environment timezone 顯示。

## 10. Definition of Done

每項 V2+ 功能完成時至少具備：

- Environment／Managed Tenant scope 與 object authorization。
- RLS／repository 正向與負向測試。
- Permission、sidebar、route 三層 gating。
- Audit event、structured telemetry、metric／alert 影響。
- 429／timeout／consent revoked／retry／idempotency 行為。
- Migration、rollback／feature disable、資料 retention 說明。
- 文件與 capability／permission catalog 更新。
