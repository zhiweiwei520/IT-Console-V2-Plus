"""
Control Plane package — 佔位，尚無實作。

02-target-architecture.md 的獨立 Control Plane 服務、Deployment Stamp placement、
provisioning worker 依 11-final-architecture.md §2.4 Gate B（商業訊號確認後）才啟動。
MVP 以 manage.py CLI 覆蓋環境 CRUD（見 ../../manage.py），Catalog／Stamp 分離前
principal_environment_index 亦未建立（環境查詢直接查 environment_memberships）。
"""
