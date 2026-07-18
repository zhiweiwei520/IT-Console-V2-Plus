# 06 — 分支、遷移與交付路線

## 1. 分支策略

目前 `main` 工作樹已有大量未提交修改。開始 V2+ 前先由維護者整理現況並建立可重現 baseline tag，避免把未完成改動錯當成 V2+ 基線。

建議：

- 現行產品：`main`，只維護既有版本與必要安全修正。
- V2+ 起始分支：`v2plus-foundation`。
- 採短生命 feature branch + PR，不建立每客戶長期分支。
- 基礎 Tenant 化穩定後，再評估把 V2+ 拆成獨立 repo；文件資料夾不是應用副本。
- V2+ migration 不回灌現行 production DB，直到明確 cutover rehearsal。

## 2. 交付階段

| Phase | 目標 | 主要產出 | Exit gate |
|---|---|---|---|
| 0 — Baseline | 凍結範圍與可驗證基線 | ADR、依賴矩陣、固定來源版本／baseline tag、資料分類、最小 CI、signed image、health／trace 骨架 | 保留／移除／重構逐項核准；PR gate 可運作 |
| 1 — Microsoft-only | 移除第三方產品耦合 | capability manifest、TV1／CTI／工具退場、Microsoft Security 拆分、同 digest promotion | 無非 Microsoft route／setting／job 被註冊 |
| 2 — Tenancy foundation | 建立 minimal Catalog、Environment／Managed Tenant | bootstrap catalog、host resolver、schema、TenantContext、membership RBAC、scoped repository、RLS | 兩 Environment 隔離測試全過 |
| 3 — Microsoft connection | 多 Tenant consent／token／quota prototype | Login App 與 Management App bundles、connection registry、capability scan | 兩個測試 Tenant 可獨立連線／撤銷；不得以 APScheduler／Web 執行 production 多 Tenant sync |
| 4 — Durable execution | Web、Dispatcher、Worker 分離 | outbox、Service Bus、lease、idempotency、DLQ、Blob reports | crash／重送／429 不重複且可復原 |
| 5 — SaaS Control Plane | 擴充完整環境生命週期 | automated placement、IaC provisioning、plan entitlement、metering、minimal Catalog 升級 | 可自動建立／停用／刪除試點環境 |
| 6 — Production readiness | 安全與營運硬化 | 完整 CI/CD、observability、BCDR、pen test、runbooks、pilot soak | GA checklist 與試點簽核 |

## 3. Legacy 資料遷移順序

1. 建立 `legacy-default` Management Environment。
2. 將現行 `azure_tenant_id` 建為第一個 Managed Tenant；先驗證 organization ID。
3. 將現行 User 轉為 Principal，建立 default Environment Membership 與顯式 role assignment。既有 `super_admin` 分別建立經核准的 platform break-glass/operator 與 `legacy-default` Environment admin 兩筆 assignment；其他角色與 direct grants 逐項 mapping，不以隱含全權取代。
4. 為 Config、Task、Schedule、Execution、Report、Audit、SystemLog、Microsoft cache 回填 `environment_id`。
5. 為 Microsoft 資料回填 `managed_tenant_id`，把裸遠端 ID 改為 composite unique。
6. 將 Entra external login 拆為 unique `(canonical_issuer, subject)`，另存 issuer Tenant／object ID。保留 local password hash 規則，但所有 legacy session 因缺 Environment binding 於 cutover 撤銷，使用者必須重新登入。
7. 以一次性受控程序將 Graph credential 搬至 Key Vault：寫入新版本 → 取 token／capability 驗證 → 切換 reference → 清除舊 DB 密文與暫存 → 保留可稽核的失敗回復點，任何 log 不輸出 secret。
8. 將報表搬至 Blob，建立 object key 與 checksum 對照。
9. 將排程轉為 job definition + targets；現行 running 工作不得跨 cutover。
10. 加入 NOT NULL、FK、RLS 與 FORCE RLS；換用非 owner app role。
11. Legacy AuditLog 全域 chain 原樣凍結至 immutable archive，不改欄位、不重新 hash；新 Environment chain 的 genesis marker 引用 legacy final hash／anchor digest，再驗證兩條證據鏈。
12. 驗證 row count、關聯、checksum、collision quarantine、權限矩陣與下載授權。
13. rehearsal 通過後採明確 write-freeze + 最終 watermark 搬遷 + 對帳 + DNS 切換；本計畫不假設已有 CDC。

被移除的 TV1、外部 CTI、工作記錄、HR／工具資料預設不搬入 V2+ 業務 schema；依保留政策匯出或放唯讀封存庫。

正式實作前建立逐表 migration mapping，至少含來源版本、owner、來源／目標欄位、轉換、default、collision／quarantine 規則、checkpoint、可重跑策略、驗證 SQL、允許差異與證據檔。Fresh install、固定 baseline upgrade、N-1 upgrade、pooled → dedicated 搬遷分開驗收。

## 4. Expand／Migrate／Contract

所有 schema 變更採三階段：

- Expand：新增 nullable 欄位／新表／雙讀能力，不破壞舊版。
- Migrate：背景回填、雙寫或 checksum 驗證，可重跑且具 checkpoint。
- Contract：確認所有 Stamp 已升級後，才設 NOT NULL、移除舊欄位／表。

禁止在同一 release 直接 rename／drop 並要求所有 Stamp 原子升級。

Control Plane 保存每個 Stamp 的 schema version、app digest、migration state 與最後成功時間。Migration 使用 advisory lock；失敗 Stamp 自動 quarantine 並停止 rollout，App 僅支援已核准的 N/N-1 schema skew。

## 5. Microsoft-only 退場檢查

每一功能必檢查：

- `app/__init__.py` Blueprint 與 startup hook
- `app/modules/*` auto discovery
- `permissions.py`、role mappings、sidebar、audit metadata
- System／Module config 與 secret keys
- scheduler system jobs 與既有 job definitions
- models、Alembic、FK、dashboard aggregate
- templates、JS、唯一 `theme.css` 內的 module selectors
- tests、README、sample、download assets
- legacy route redirect 與資料 export

## 6. Cutover 與 rollback

切換前：

- 完成至少一次 production-like rehearsal。
- 驗證舊系統無 running job；停止 scheduler 與新寫入。
- 備份 DB、Blob／report、audit anchor 與設定 reference。
- 執行增量 migration 與對帳。
- 驗證兩個不同 Environment 的正反向隔離案例。

Rollback 僅限 write-freeze 尚未解除、V2+ 尚未接受新寫入的回切窗口。V2+ 一旦接受新寫入，本計畫沒有 reverse-sync／CDC 設計，預設只能 forward-fix；若業務要求資料回切，須先另立 reverse-sync Epic、逐表逆向 mapping 與演練，不得只改 DNS 造成資料分叉。

## 7. 初步工作量與相依順序

不在需求、隔離模式與 consent 模式未定案時給單一工期承諾。建議先做 2–3 週工程 spike，交付：

- TenantContext + 一個 Blueprint（建議 accounts）Tenant 化垂直切片。
- PostgreSQL RLS prototype 與 connection pool 驗證。
- 兩個測試 Entra Tenant 的 consent/token prototype。
- Service Bus fan-out + idempotent worker prototype。
- pooled 與 dedicated DB 的成本／操作比較。
- 固定來源 baseline 的逐表 mapping 範例、legacy audit transition 與 write-freeze cutover rehearsal。

Spike 完成後再用實測 throughput、schema 影響表與 Azure 成本估算 Phase 2–6。
