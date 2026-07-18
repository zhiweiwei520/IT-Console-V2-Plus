# 01 — 現況評估與功能範圍

## 1. 現行架構基線

現行系統是 Flask Application Factory 單體應用，SSR、JSON API、背景排程與 Worker 執行皆在同一程式內：

- 應用組裝：`app/__init__.py`
- Blueprint：`app/blueprints/*`
- 可探索模組：`app/core/module_registry.py`、`app/modules/*`
- ORM：`app/models/*`
- Microsoft API：`app/services/*`、`app/utils/graph_client.py`、`app/utils/token_manager.py`
- 排程與執行：`app/scheduler/scheduler_service.py`、`app/services/task_service.py`
- 認證／RBAC：`app/blueprints/auth/*`、`app/models/user.py`、`app/core/permissions.py`
- 資料庫：PostgreSQL 已可用，但仍保留 SQLite 開發相容與部分 runtime schema helper。

現行優點可直接延續：

- Blueprint + Module Plugin 分層已具模組邊界。
- Graph 呼叫已有分頁、批次、Retry-After、節流與 adaptive controller 基礎。
- 本地登入、Entra SSO、CSRF、Session 撤銷、RBAC、append-only 稽核已有完整流程。
- PostgreSQL、Alembic、分層測試與 Docker 基礎已存在。

## 2. 功能處置矩陣

| 現行功能 | V2+ 處置 | 目標定位 | 主要程式範圍 |
|---|---|---|---|
| 帳號／納管網域 | 保留並 Tenant 化 | Entra 使用者、網域、群組、角色 | `accounts`、`account_service.py` |
| 授權／MFA 稽核 | 保留並 Tenant 化 | Entra／M365 合規稽核 | `licenses`、`license_mfa` |
| 登入記錄 | 保留並 Tenant 化 | Entra sign-ins 查詢與同步 | `signin_logs`、`entra_signin_sync_service.py` |
| 應用程式稽核 | 保留並 Tenant 化 | App Registration／Enterprise App 稽核 | `app_audit` |
| Intune 裝置／軟體 | 保留並 Tenant 化 | Endpoint 與 detected apps | `devices`、`software`、`intune_service.py` |
| Teams／SharePoint | 保留並 Tenant 化 | M365 管理與治理快取 | `teams*`、`sharepoint*` |
| Defender／Log Analytics | 保留並拆分 | Microsoft Security／Azure Monitor | `defender_sync_service.py`、`soc_entra_log_query_service.py` |
| Dashboard | 重構 | 依環境、Tenant 與授權聚合 | `dashboard*` |
| 任務／排程／報表 | 重構為平台底座 | durable queue、fan-out、Blob 報表 | `tasks`、`scheduler`、`reports` |
| 認證／RBAC／稽核 | 保留機制、重構資料域 | 平台與環境兩層授權 | `auth`、`settings`、`user.py` |
| SOC Preview | 拆分重命名 | 只保留 Entra／Defender／Azure Monitor | `soc_preview`、`soc_*` |
| 資料管理 | 拆分 | 保留 Entra／Intune 資產能力；HR 主檔另決策 | `data_management`、`device.py` |
| Trend Vision One | 移除 | 不進 V2+ | `trend_vision_one*`、TV1 modules/models |
| 外部 CTI／Threat Intel | 移除 | 不進 V2+；日後可另做 Sentinel TI | `threat_intel*`、`soc_cti_*` |
| 工作記錄 | 移除 | 非 Entra／Azure 產品核心 | `work_records*` |
| 系統工具 | 移除 | PE／CSV／IIS／EVTX／Email Header 等不進產品 | `system_tools*` |
| 網管／憑證預留入口 | 移除 | 尚未實作且不屬本次核心 | `network.view`、`certificates.view` |
| PWA、系統監控、備份 | 保留並雲端化 | 平台技術能力 | `pwa`、monitoring、backup |

### 移除原則

不直接刪資料表或 Blueprint。依序執行：

1. 建立 capability manifest 與依賴測試。
2. 關閉 UI、權限與新任務建立。
3. 停止排程與新資料寫入。
4. 提供資料匯出／封存與保留期。
5. 移除 route、service、module、setting、permission、template、static asset。
6. 經至少一版相容期後再以 migration drop schema。

`EntraSigninCache` 目前放在 `app/models/threat_intel.py`，必須先搬到 Microsoft 專屬模型後，才能移除 Threat Intel。

## 3. SaaS 阻塞缺口

| 等級 | 缺口 | 現況風險 | 必要處理 |
|---|---|---|---|
| P0 | 無環境／Tenant scope | 任一漏 filter 都可能跨客戶洩漏 | Request context + scoped repository + RLS |
| P0 | SSO 與 Graph 共用憑證 | 高權限與登入責任混雜 | 拆成 Login App 與 Management App |
| P0 | 全域 unique ID | 不同 Tenant 的 OID／Graph ID 可能衝突 | 改為含 issuer／managed tenant 的複合鍵 |
| P0 | 全域 super_admin | 平台人員可自然穿透客戶資料 | Platform role 與 Environment role 分離 |
| P0 | 本機報表／cache／anchor | 無法獨立備份、刪除與授權 | Blob 分區、每環境稽核鏈與金鑰 |
| P1 | APScheduler／進度／取消在記憶體 | 僅能單 Worker，重啟即中斷 | Service Bus + durable execution state |
| P1 | Token／OAuth state／hot cache 在記憶體 | 多節點不一致或跨 Tenant 汙染 | Tenant-aware key + Redis／DB |
| P1 | Web 啟動混入 schema 修補 | 多 Stamp 升級不可控 | Alembic one-off migration job |
| P1 | 缺集中可觀測性 | 無法依客戶／Tenant 判斷 SLO | OpenTelemetry + Application Insights |
| P2 | 相依套件使用 `>=` | Build 不可重現 | 鎖版、SBOM、映像簽章 |

## 4. 不建議的方案

- 為每個客戶複製一份程式分支：會產生版本漂移與無法批次修補的安全風險。
- 只靠 URL 或前端 hidden field 傳 `environment_id`：租戶邊界不可由客戶端決定。
- 只在 route 加 `.filter_by(environment_id=...)`：背景工作、匯出與新路由仍會漏；必須有 DB RLS 防線。
- 每個 Entra Tenant 都建立一套硬編碼 service class：應以 `TenantContext` 與 connection provider 注入。
- 在 Web process 繼續執行高成本同步：無法水平擴充，也會讓單一 Tenant 影響互動流量。

## 5. 範圍外

- 本階段不實作計費、Microsoft Marketplace 上架或稅務流程。
- 不承諾跨客戶整體資料分析；Control Plane 僅保存營運 metadata 與計量，不保存客戶業務內容。
- 不保留 Trend Vision One 或其他第三方 provider 的抽象相容層。
- 不在首版導入 AKS；除非 Container Apps 的限制經壓測證實不足。

