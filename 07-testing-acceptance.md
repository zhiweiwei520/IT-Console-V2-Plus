# 07 — 測試策略與驗收門檻

## 1. 核心原則

跨 Environment／Tenant 資料洩漏是 release blocker，不能以「已知問題」上線。每個功能需同時驗證 route、service／repository、DB RLS、background worker 與 Blob authorization。

## 2. 測試層級

| 層級 | 內容 | 執行時機 |
|---|---|---|
| Unit | TenantContext、permission、key builder、state machine、idempotency | 每 PR |
| Repository／RLS | Environment／Tenant filter、USING／WITH CHECK、pool reset | 每 PR／PostgreSQL job |
| Web | host resolution、membership、IDOR、CSRF、source minimization | 每 PR 受影響 profile |
| Worker | fan-out、lease、retry、cancel、DLQ、checkpoint | 每 PR 受影響 profile |
| Contract | Graph response、permission degradation、delta／paging、429 | Nightly；錄製的去識別 fixture |
| Integration | PostgreSQL、Service Bus emulator/test namespace、Blob、Key Vault reference | Nightly／release |
| E2E | onboarding → consent → sync → report → revoke → offboard | release candidate |
| Security／Load／Chaos | isolation fuzz、SAST/DAST、noisy neighbor、worker crash | release／定期 |

現有 `quick/smoke/web/data/full` profile 繼續使用；新增 `tenancy`、`worker`、`migration`、`azure-contract` profile。測試 DB 不得接觸 live database。

## 3. 必測隔離案例

建立 Environment A／B，各有 Tenant 1／2，並刻意使用相同 display name、不同 issuer 下相同 raw object ID 與相同檔名。若 D-03 允許 Environment-local login，再額外測試相同 local username：

- A 使用者不能 list、detail、search、export、download、update、delete B 的資料。
- A 即使提交 B 的 Environment UUID、Managed Tenant UUID、record ID 或 Blob key 仍失敗。
- A 的 Tenant 1 grant 不能查看同 Environment 的 Tenant 2；具有 all-tenant grant 者在一般管理畫面仍須一次只選一個 Tenant，不得同時聚合。
- query string／form 偽造另一個 `managed_tenant_id` 不得改變 session 鎖定的目前 Tenant；同步工作也只能使用目前 Tenant。
- 切換 Environment、登出、membership version 失效會清除目前 Tenant；未選 Tenant 的業務 route fail-closed 並導向選擇頁。
- 合法跨 Tenant 報表必須走獨立 route／service，顯式驗證完整 grants，且不得重用一般管理清單 repository。
- RLS 在沒有 context、錯誤 context、INSERT／UPDATE 跨 Environment 時 default deny。
- DB connection 歸還 pool 後不保留前一個 tenant setting。
- Cache、token、delta link、rate limit、progress、cancel flag 不跨 Tenant 命中。
- 同一 Graph object ID 可安全存在兩個 Managed Tenant。
- Platform operator 未取得 JIT grant 時不能讀客戶資料。
- Environment suspend／membership revoke 後既有 session 在核准時限內失效，未開始 job 不再執行；暫定 p95 ≤ 60 秒。
- 未授權者無法取得報表 stream／SAS；單一 blob 的短效 SAS 無法讀其他 object。SAS 本身是 bearer capability，不測試「不可重用」。

## 4. 背景工作案例

- 同一訊息重送 2 次不產生重複 cache／result／report。
- Worker 在 Graph page 途中 crash，lease 到期後能從安全 checkpoint 重試。
- Tenant A 連續 429 時，Tenant B 工作仍在配額內前進。
- `Retry-After` 被遵守；batch subrequest 429 分別重試。
- Consent revoked／credential expired 轉 connection state 並停止無限 retry。
- 多個 dispatcher 同時啟動只 enqueue 一次到期工作。
- cancel、timeout、DLQ replay、partial batch summary 正確。
- Queue 訊息 environment／tenant 與 DB execution 不符時 fail-closed 並告警。

## 5. Migration 驗證

- 從 Phase 0 鎖定的 baseline tag／schema 及明列的 N-1 版本分別升級至目標版。
- Expand 期間新舊版應用可同時運作於相容窗口。
- 回填可重跑、具 checkpoint、不中斷已完成資料。
- 每表 row count、FK orphan、unique collision、timestamp、JSON／Text、sequence 對帳。
- Microsoft remote IDs 轉複合鍵後關聯不遺失。
- Report Blob checksum 與 DB metadata 一致。
- Legacy audit chain 與 anchor 原樣可驗證；新 Environment genesis marker 正確引用 legacy final hash／anchor digest，未重新 hash 舊紀錄。
- Legacy active sessions 全數撤銷；新登入 session 具 Environment binding。
- Rollback rehearsal 不產生 DB／Blob 分叉。

## 6. 安全驗收

- OWASP ASVS 對應清單與 threat model review 完成。
- Secret／dependency／SAST／container scan 無未核准 high／critical。
- Token、secret、UPN、raw Graph evidence 不出現在 log、trace、queue、exception page。
- OAuth state replay、open redirect、host-header injection、subdomain takeover、CSRF、SSRF 測試通過。
- Support JIT、break-glass、role escalation、direct permission grant 皆具 audit 與告警。
- Azure resource public access、RBAC、private endpoint、Key Vault purge protection 符合 IaC policy。

## 7. 效能與 SLO 驗收

- Phase 0 結束前先核准數值化 SLO／RPO／RTO 與容量預測；以下為 spike 暫定工程門檻，D-10 可調整但不得留白進 Pilot。
- 以已核准 12 個月預估 Environment／Tenant／資料量與峰值的 2 倍做容量測試。
- 同時測試互動查詢與大型同步，確認 Worker 不拖慢 Web。
- 量測 Graph 429、queue age、checkpoint lag、DB pool、RLS query overhead。
- Tenant A 持續 429／滿載時，Tenant B 同型工作吞吐暫定維持無干擾 baseline 的 ≥ 90%。
- 暫定 interactive queue age p95 < 60 秒、scheduled queue age p95 < 5 分鐘、Worker crash 後 lease recovery < 5 分鐘；DLQ 事件 30 分鐘內被 on-call acknowledgement。
- 暫定 MVP RPO ≤ 15 分鐘、RTO ≤ 4 小時；以實際 restore drill 證明，不以服務規格推算。
- Migration 安全／權限／FK／row ownership mismatch 必須為 0；其他資料差異只有逐表 mapping 已核准者可接受，checksum 規則須可重現。
- dedicated DB／Stamp 可在不改程式碼下完成 placement 與 smoke test。

Pilot 最低包含 2 個 Environment、每個至少 2 個 Managed Tenant、每個至少 3 位不同角色使用者，連續 soak 14 天；期間不得有跨租戶事件、Sev-1／Sev-2 未解缺陷，排程工作成功率暫定 ≥ 99%。

## 8. Release gate

Release candidate 必須：

1. `quick + web + data + tenancy + worker + migration + full + azure-contract` 全數通過，無未核准 skip；`full/azure-contract` 可由同 commit／同 image digest 的有效 nightly evidence 滿足。
2. PostgreSQL 實例上的 RLS 與 migration matrix 通過。
3. 兩個測試 Entra Tenant 完成 consent、同步、撤銷與重新同意。
4. BCDR、worker crash、Graph 429、DLQ replay 至少各演練一次。
5. 隔離測試與 security scan 無 release blocker。
6. 變更、rollback、support、offboarding runbook 經雙人審查。
7. 數值化 SLO／RPO／RTO、alert owner、Pilot soak 與退出條件有簽核 evidence。
8. Requirement → ADR → Epic → Test → Evidence → Owner traceability matrix 無 P0 缺口。
