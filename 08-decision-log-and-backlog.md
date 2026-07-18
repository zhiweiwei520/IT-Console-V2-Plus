# 08 — 決策紀錄與開發 Backlog

## 1. 前置決策草案

| ID | 決策 | 狀態 | 理由 |
|---|---|---|---|
| ADR-001 | 固定 Environment → Managed Tenant 雙層模型 | Proposed | 避免「Tenant」語意混用，符合獨立管理環境需求 |
| ADR-002 | 共享 Control Plane + Deployment Stamps | Proposed | 同時支援 pooled 與 dedicated，便於擴充與部署 rings |
| ADR-003 | 保留 Flask 模組化單體，拆出 Dispatcher／Worker | Proposed | 降低重寫風險，同時解除單 Worker 限制 |
| ADR-004 | 平台 Login App 與受管 Graph App bundles 分離 | Proposed | 權限最小化與縮小 credential blast radius |
| ADR-005 | Environment + Managed Tenant RLS 與 scoped repository 雙防線 | Proposed | 防止漏 filter 導致跨客戶洩漏 |
| ADR-006 | 純 Microsoft，不保留第三方 provider abstraction | Proposed | 避免為已移除功能維護不必要複雜度 |

正式開發前應將每項轉為獨立 ADR，補上 alternatives、consequences、owner 與核准日期。

## 2. 必須由產品／架構決策

| ID | 問題 | 建議預設 | 影響 |
|---|---|---|---|
| D-01 | Environment 隔離方案 | 標準 pooled+RLS；企業 dedicated DB／Stamp | 成本、RPO/RTO、營運工具 |
| D-02 | Graph connection／permission bundle | Provider-owned versioned bundles 起步，保留 BYO app | Consent UX、credential、re-consent、測試矩陣 |
| D-03 | Environment 管理者登入 | 支援客戶 Entra SSO；明確決定是否也保留 Environment-local 帳號；平台本地登入為 break-glass | Identity schema、issuer、網域、既有 UX |
| D-04 | HR 資料管理 | 不進核心；另做選配前需個資評估 | schema、保留期、產品定位 |
| D-05 | Microsoft-only SOC 範圍 | Entra + Defender + Azure Monitor；改名 | 權限、UI、歷史資料 |
| D-06 | 跨 Tenant 聚合 | 允許，但需 all-tenant grant | 報表、資料最小化 |
| D-07 | Support 存取 | 預設禁止，JIT + 客戶核准 | 支援流程、稽核 |
| D-08 | 資料駐留區域 | Customer Content 固定 region；identity、Catalog、audit、telemetry、backup 分類揭露 | Catalog、Stamp、合約、搬遷 |
| D-09 | 保留／刪除／legal hold | 依方案；先定預設與最大值 | 儲存成本、法遵 |
| D-10 | SLA／RPO／RTO | Spike 與 restore drill 後承諾 | Azure topology、價格 |
| D-11 | Sovereign Cloud | MVP Azure Public only | Endpoint allowlist、App registration |
| D-12 | 計價單位 | Environment + Managed Tenant + job／storage | entitlement、metering、商務 |
| D-13 | 授權資料拓樸 | Principal 在 Control Plane；authoritative Membership／roles／grants 在 Data Plane，Catalog 只存 routing index | 跨 DB FK、projection、一致性、撤權 |
| D-14 | 中央 Auth Broker／Session | 固定 callback + 一次性 handoff + host-only signed cookie + DB active-session registry | 子網域登入、切換、logout、撤銷 |
| D-15 | Blob 下載模式 | 敏感檔 proxy stream；大型檔極短效單 blob user-delegation SAS | 效能、bearer URL、audit |
| D-16 | Pipeline 與相容版本 | Protected CI、OIDC、build-once digest promotion、N/N-1 schema | 供應鏈、rollout、回復 |

## 3. Epic Backlog

### EPIC-01 — Product boundary

- 建 capability manifest：module、route、permission、setting、model、job、UI、test。
- 完成 Microsoft／remove／archive 標記與 owner 核准。
- 將 Entra cache 從 Threat Intel 模型移出。
- 拆 Microsoft Security provider；退場 TV1／CTI／work records／system tools。

### EPIC-02 — Tenancy kernel

- 建 Environment、ManagedTenant、Principal、Membership、Role、Grant schema。
- 實作 host resolver、TenantContext、membership version 與環境切換。
- 建 scoped repository base 與 object authorization helper。
- 實作 PostgreSQL RLS、app DB role 與 isolation tests。
- 實作 minimal Catalog／Environment projection、verified host 與 origin bypass 防護。

### EPIC-03 — Identity and RBAC

- 遷移 local user／password；legacy session 全撤銷，不遷移。
- External login 改 unique `(canonical_issuer, subject)`，禁止 email／UPN fallback linking。
- 建 Central Auth Broker、固定 callback、一次性 Environment handoff 與 host-only session。
- Platform role 與 Environment role 分離。
- 實作 JIT support grant、break-glass policy 與 audit。

### EPIC-04 — Microsoft connection

- 分離 Login App／versioned Management App bundles。
- 建 Managed Tenant onboarding／Admin Consent state machine。
- 實作 capability scan、connection health、re-consent／disconnect。
- 建 Tenant-aware Token Broker、cloud endpoint allowlist、credential rotation。

### EPIC-05 — Data tenantization

- Config、Task、Schedule、Execution、Report、Audit、Log 加 Environment scope。
- 所有 Microsoft cache／checkpoint 加 Managed Tenant scope。
- 改 composite unique／FK／index。
- 搬報表至 Blob；重構每 Environment audit chain／anchor。
- Legacy audit chain immutable archive + 新 chain transition marker，不重新 hash。

### EPIC-06 — Durable jobs

- execution batch／tenant execution／outbox schema。
- Scheduler dispatcher leader election／claim。
- Service Bus payload contract、Worker lease／heartbeat／idempotency／cancel。
- Per-Tenant quota、Retry-After、circuit breaker、DLQ replay。

### EPIC-07 — SaaS Control Plane

- Tenant Catalog、Stamp placement、Environment lifecycle API。
- Bicep modules、provisioning operation、domain／certificate automation。
- Plans、entitlements、usage metering、suspend／offboard。
- pooled → dedicated placement／migration 工具。

### EPIC-08 — Production readiness

- OpenTelemetry、Application Insights、dashboards、alerts、SLO。
- Lockfile、SBOM、scan、signing、CI/CD rings。
- BCDR、data export／deletion、incident／support runbooks。
- Pen test、load／chaos test、pilot onboarding。

### EPIC-09 — Delivery foundation（Phase 0 起持續）

- 選定 pipeline、branch protection、required checks、OIDC、approval 與 artifact retention。
- 建 health probes、基礎 OpenTelemetry、Bicep lint／what-if 與 migration job。
- Build once／sign once，依 rings promotion 同一 image digest。
- 維護 schema version registry、N/N-1 skew 與失敗 Stamp quarantine。

## 4. 開發啟動 Definition of Ready

- D-01、D-02、D-03、D-04、D-05、D-08、D-13、D-14、D-15、D-16 已核准。
- 至少兩個非 production Entra Tenant 可供 consent／撤銷測試。
- V2+ baseline commit／tag 已建立，dirty worktree 已由維護者整理。
- Azure sandbox subscription、命名／tag／budget／region 已核准。
- 資料分類、預設 retention、support access policy 已有 owner。
- Threat model、ERD、permission catalog、Graph endpoint inventory 已審查。
- 固定 migration 來源版本、逐表 mapping template、數值化 SLO／RPO／RTO 與 Pilot 規模已有 owner。
- Requirement → ADR → Epic → Test → Evidence → Owner traceability matrix 已建立。

## 5. 前置 Spike 驗收

- Accounts 垂直切片可在同一 Environment 切兩個 Managed Tenant。
- 另一 Environment 使用者無法以任何 route／ID／DB query 讀到該資料。
- Provider App bundle 在兩個全域唯一 Tenant 完成 consent，撤銷其中一個不影響另一個；共享 connection 例外另測連動撤銷。
- Service Bus 重送／Worker crash 不重複寫資料。
- pooled RLS 與 dedicated DB 共用同一 repository API。
- 產出 Azure 成本、吞吐與操作複雜度比較，供正式估時。
