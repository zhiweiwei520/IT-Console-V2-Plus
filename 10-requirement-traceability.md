# 10 — 需求與交付證據追蹤

此矩陣是規劃基線。Owner 目前以角色表示；Phase 0 必須指派實際負責人與核准人，且每個 Evidence 連到版本化產物。

| Req | 需求／風險 | 決策 | Epic | 最低測試 | 必要 Evidence | Accountable role |
|---|---|---|---|---|---|---|
| R-01 | 純 Entra／Azure／Microsoft 版本 | ADR-006、D-04、D-05 | EPIC-01 | capability registration、legacy route 退場、schema archive | 核准 capability manifest、移除清單、資料封存清冊 | Product Owner |
| R-02 | 沿用現行平台管理認證 | D-03、D-14 | EPIC-03 | local／Entra regression、中央 callback、handoff replay、session revoke | Auth ADR、登入矩陣、security test report | Security Architect |
| R-03 | 個別獨立 Management Environment | ADR-001、ADR-002、D-01 | EPIC-02、EPIC-07 | cross-environment IDOR／RLS／Blob、suspend／offboard | Isolation test report、ERD、IaC what-if | Solution Architect |
| R-04 | 每 Environment 管理多個 Entra Tenant／多使用者 | ADR-001、ADR-005、D-06、D-13 | EPIC-02、EPIC-05 | Tenant grants、same source ID、跨 Tenant aggregate | Permission matrix、RLS policy report、E2E report | Application Lead |
| R-05 | 平台登入與受管 Graph 權限分離 | ADR-004、D-02 | EPIC-04 | login token audience、bundle consent、re-consent、revocation | App／permission inventory、consent screenshots／logs、threat review | Identity Lead |
| R-06 | SaaS pooled 與 dedicated 共用產品版本 | ADR-002、D-01、D-16 | EPIC-07、EPIC-09 | pooled → dedicated、同 image digest、N/N-1 schema | Signed digest、deployment records、migration report | Platform Lead |
| R-07 | 多 Tenant 工作不可互相拖累 | ADR-003 | EPIC-06 | 429 noisy-neighbor、idempotency、crash／lease、DLQ | Load／chaos report、queue metrics、replay record | Worker Lead |
| R-08 | 客戶資料與報表不可跨界 | ADR-005、D-15 | EPIC-02、EPIC-05 | object auth、RLS WITH CHECK、stream／SAS、cache pollution | Negative test suite、Blob access review | Security Lead |
| R-09 | 所有高風險變更可追溯 | D-07、D-13 | EPIC-03、EPIC-05 | mutation／audit atomicity、JIT support、legacy chain transition | Audit verifier output、JIT session record、anchor evidence | Compliance Owner |
| R-10 | Legacy 可安全遷移與回復 | D-01、D-16 | EPIC-05、EPIC-09 | fixed baseline、N-1、fresh install、write-freeze rollback | 逐表 mapping、對帳、cutover／rollback rehearsal | Data Migration Lead |
| R-11 | 可營運、可觀測、可還原 | D-08、D-09、D-10、D-16 | EPIC-08、EPIC-09 | probes、alerts、restore、Stamp evacuation、pilot soak | SLO sheet、restore report、runbook drill、pilot signoff | SRE Lead |
| R-12 | 供應鏈與部署一致 | D-16 | EPIC-09 | required checks、Bicep what-if、scan、digest promotion | Pipeline run、SBOM、signature、approval history | DevSecOps Lead |

## Evidence package 規則

- 每個 Phase exit 產生不可變的 evidence index，包含 commit、image digest、schema version、環境、時間、執行人與核准人。
- 測試報告需列出 passed、failed、skipped；未核准 skip 視同失敗。
- IaC evidence 包含 lint、what-if、Azure Policy 結果與實際 deployment operation ID。
- Migration evidence 包含來源／目標版本、逐表 row count、checksum、quarantine、執行 checkpoint 與 rollback eligibility。
- Security evidence 不附 token、secret 或客戶 raw payload；必要識別值採 pseudonymization。
- ADR、Epic 或需求變更時，同一 PR 必須更新此矩陣與受影響測試／evidence 定義。

## Phase exit 簽核

| Phase | 最低簽核角色 |
|---|---|
| 0／1 | Product Owner、Solution Architect、Security Architect |
| 2／3 | Application Lead、Identity Lead、Security Lead |
| 4 | Worker Lead、SRE Lead、Security Lead |
| 5 | Platform Lead、Data Migration Lead、Product Owner |
| 6／GA | Product Owner、Security／Compliance、SRE、Release Manager |

