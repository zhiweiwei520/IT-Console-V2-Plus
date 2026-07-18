# 05 — 安全與營運基線

## 1. 威脅模型重點

| 威脅 | 控制 |
|---|---|
| 以 URL／UUID 存取其他 Environment | host-derived context、object authorization、scoped repository、RLS、跨環境回 404 |
| 繞過 Front Door／偽造 Host | origin Private Link／access restriction、Front Door instance 驗證、verified-domain unique catalog、direct origin fail-closed |
| Graph ID 在不同 Tenant 碰撞 | `(managed_tenant_id, source_object_id)` 複合唯一鍵與 FK |
| 平台管理員濫用 | Control Plane role 與客戶資料權限分離；JIT、客戶核准、理由、到期、audit |
| Queue 訊息竄改／錯投 | Managed Identity、Service Bus RBAC、server-side context revalidation、訊息不帶 secret |
| Token／憑證外洩 | federation／憑證、Key Vault、短效 token、redaction、credential version rotation |
| 快取跨 Tenant 汙染 | 強制 environment／tenant key prefix、typed cache wrapper、負向隔離測試 |
| Noisy neighbor | 每 Environment／Tenant 配額、queue fairness、Worker concurrency、429 circuit breaker |
| 報表／Blob IDOR | 每 Environment 私有 container、Storage Broker、每次下載 object authorization、隨機 key |
| 支援人員無痕查看 | 禁止常駐 data access；JIT support session 與不可變稽核 |
| OAuth callback replay | 一次性 server-side state、nonce、TTL、environment／redirect binding |

## 2. 認證安全

沿用現有機制時保留：PBKDF2 密碼雜湊、失敗鎖定、anti-enumeration、IP allowlist、CSRF、Flask signed-cookie session + DB active-session registry／撤銷、閒置逾時。

必要調整：

- 本地 `/dma` 建議定位為平台 break-glass；僅 private endpoint／VPN／受控 IP，啟用即告警。Environment 管理者是否保留本地登入由 D-03 定案。
- Customer Environment 的日常管理者優先使用 Entra SSO 與其 Conditional Access／MFA。
- Session 記錄 active environment、membership version 與 auth strength；Environment suspend／membership revoke 的暫定 p95 失效目標為 60 秒內，正式值由安全 ADR 核准。
- Cookie 使用 Secure、HttpOnly、SameSite；避免跨客戶子網域共享 Domain cookie，優先 `__Host-` 規則。
- 高風險操作要求 recent authentication，並可在 GA 前加入 step-up policy。

## 3. 授權與支援存取

- Platform permissions：環境建立、停用、placement、方案、平台健康度。
- Environment permissions：使用者、角色、Managed Tenant、模組、工作、報表、稽核。
- Tenant grants：全部 Tenant 或明確 subset。
- Object authorization：下載、重跑、刪除、查看明細均驗證物件所屬 Environment／Tenant。
- Support access 預設關閉；啟用時產生時效性 access grant，記錄申請人、核准人、原因、工單、開始／結束與所有操作。
- 禁止「platform_operator 隱含所有 Environment permission」。

## 4. Secrets 與金鑰

- Azure 資源存取以 Managed Identity + Azure RBAC 為主。
- Provider Graph App 使用 workload identity federation 或 Key Vault certificate。
- BYO App 只保存 `credential_ref`；不將可逆密文存 `SystemConfig`。
- 每 Environment 至少使用獨立 data-encryption／audit-signing key scope；專屬方案使用獨立 Key Vault。
- 設定 credential expiry、rotation window 與失敗告警；輪替支援新舊版本重疊。
- Key Vault soft delete、purge protection、private endpoint 與 diagnostic logs 必須啟用。

Microsoft 最新 Key Vault 安全建議偏向在多租戶 SaaS 中採更細的 vault 隔離；V2+ 以 Environment 為客戶安全邊界，是否一環境一 Vault 由隔離方案 ADR 定案：[Key Vault security](https://learn.microsoft.com/en-us/azure/key-vault/general/security-features)。

## 5. 稽核與資料保護

現行單一 AuditLog hash chain 與本機 anchor 不適合多 Environment 併發。V2+ 應分為：

- Platform audit：Control Plane 與 provisioning 操作。
- Environment audit：客戶環境內的人員、設定、Tenant、工作與資料操作。
- 每 Environment 獨立 chain／signing key；寫入以 row lock 或 advisory lock 序列化 chain head。
- 一般 app role 對 audit table 不具 UPDATE／DELETE；專用 chain writer 只允許 append，驗證與維護使用分離 role。
- anchor 定期寫入具 immutability policy 的 Blob；驗證工作可獨立執行。
- audit detail 不保存 token、secret 或不必要的 raw Graph payload。
- 高風險 DB mutation 必須與 audit／outbox 在同一 transaction 成功，audit 失敗則 mutation rollback；外部 Microsoft side effect 使用 durable operation，先寫意圖／outbox，再寫結果 audit。讀取與匯出的 audit fail-open／fail-closed 由 action 等級表明確定義。
- Legacy 全域 chain 不拆分、不改寫、不重新 hash；原 DB／anchor／驗證 key 以 immutable archive 保存，新 Environment chain 的 genesis marker 引用 legacy final hash 與 anchor digest。
- 所有時間 DB 寫入仍採 naive UTC；顯示固定 Asia/Taipei 的既有規範若產品未改全球化可延續。SaaS 全球化前須把 display timezone 改為 Environment 設定，但儲存仍為 UTC。

資料分類至少包含：Public、Internal、Customer Metadata、Customer Content、Credential、Audit。每個類別定義 encryption、retention、export、support access 與 deletion SLA。

## 6. 可觀測性

Telemetry 依 cardinality 分流：

```text
Metrics: region, stamp_id, plan, operation, resource, outcome（低基數）
Trace/log: environment_id, managed_tenant_id, batch_id, execution_id, correlation_id
Security audit only: principal_id、support grant、敏感授權事件
```

禁止把 Principal、Environment、Tenant 或 Execution ID 當 metric dimension。每 Environment SLO 由受控 log／trace 派生或 bounded aggregation 產生，避免 App Insights 高基數與成本失控。

Graph 故障另記 request-id、client-request-id、resource、status、retry-after；不得記完整 URL query、access token、credential 或 raw response。

核心 metric／告警：

- 登入失敗、break-glass 使用、membership／consent 變更。
- Graph token error、429 rate、5xx、circuit open、checkpoint lag。
- Queue age、DLQ depth、worker lease timeout、scheduler lag、job failure ratio。
- DB connection pool、RLS denial、slow query、storage error。
- 每 Environment SLO 與配額使用率；平台 aggregate 不含客戶內容。
- 稽核 chain／anchor 驗證失敗。

Sampling、retention、PII pseudonymization、alert threshold 與 alert owner 必須納入 Environment／Stamp 營運設定；安全 audit 不可被一般 trace sampling 丟棄。

## 7. 備份、還原與刪除

- PostgreSQL：PITR、定期 restore drill；dedicated DB 可單環境還原。
- Pooled DB：不可用整庫還原直接覆蓋 production；需環境級 export／selective restore 工具。
- Blob：versioning、soft delete、immutability 僅用於需要的 audit container。
- Key Vault：rotation 與 recovery 演練；Environment deletion 前確認法定保留。
- Offboarding：停止工作 → 撤 session／停用本地 connection 與 token → 客戶匯出 → 提示並驗證客戶管理員撤銷 Enterprise App consent → retention hold → 刪 DB rows／Blob／keys → 產生 deletion certificate metadata。除非另有最小權限 ADR，平台不為自動撤 consent 申請高權限。
- RPO／RTO、資料保留、legal hold 與刪除期限須依方案與法遵定案。

資料駐留需分別列出 Customer Content、identity／membership、Catalog metadata、audit、telemetry 與 backup 的實際區域；共享 global Control Plane 若跨區保存個資，必須在產品與合約揭露，不能只以 Environment region 概括。

## 8. CI/CD 與供應鏈

- 相依套件建立 lock／constraints，不再只依 `>=` 建 production image。
- Phase 0 即建立最小 pipeline。Pipeline 平台（GitHub Actions 或 Azure DevOps）由 ADR 選定；啟用 protected branch、required checks、OIDC／workload identity service connection、受保護環境 approval 與 artifact retention。
- PR：quick + 受影響 profile + Bicep lint／what-if + 漸進導入的 lint／type／security checks。
- Nightly：full + PostgreSQL + RLS／隔離 + migration matrix。
- Release：SBOM、dependency／container scan、secret scan、映像簽章、provenance。
- CD：Bicep 建資源；migration 以具 lock、dry-run 與失敗 quarantine 的獨立 one-off job 執行，禁止 Web startup `create_all()`／補欄位。
- Build once：所有 rings 推進同一 signed image digest，不得在各環境重建。部署前檢查 Stamp schema registry 與允許的 N/N-1 相容範圍，超出最大 schema skew 即停止 rollout。
- 部署 rings：internal → canary Stamp → standard Stamp → dedicated Stamp；migration 必須 expand／migrate／contract 相容。
- 不維護客戶專屬程式版本；差異使用 entitlement、config 或 feature flag。

Dependency／scan 例外必須具 owner、理由、到期日與修補版本；integration test namespace 需獨立、定期清理並設 Azure budget。

## 9. 服務健康與營運責任

- Web 提供不含客戶資料的 liveness 與 readiness；readiness 驗證必要 DB／session registry，Graph 失效只讓對應 capability degraded，不拖垮整站。
- Worker 提供 heartbeat、lease 與 graceful shutdown；部署時停止取新訊息、完成或安全 checkpoint 後 drain，逾時才 abandon。
- Dispatcher 監控 leader／claim、scheduler lag 與 outbox age；Redis／Service Bus／Catalog 故障行為需逐項定義 fail-open／closed。
- Pilot 前完成 RACI、on-call、事件分級、升級路徑、客戶通知與狀態頁 owner。
- 必備 runbook：Catalog、PostgreSQL、Redis、Service Bus、Key Vault、Graph 429、consent revoked、DLQ、憑證輪替、Stamp evacuation、RLS／跨租戶事件、restore、offboarding。
