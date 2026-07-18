"""
時間 helper。鐵則（CLAUDE.md B2 / 09-development-standards.md §7）：
DB 一律存 naive UTC；顯示層一律 UTC+8（Asia/Taipei），由 `to_taipei_str` 統一轉換。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# Taipei 固定 UTC+8、無 DST → 固定位移即正確，不為顯示引入 tzdata 依賴。
_TAIPEI_OFFSET = timedelta(hours=8)
_FRACTION = re.compile(r"\.(\d+)")


def utc_now_naive() -> datetime:
    """DB 寫入用：naive UTC 現在時間（無 tzinfo，避免與既有 naive 欄位比較出錯）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_taipei_str(value, fmt: str = "%Y-%m-%d %H:%M"):
    """顯示層統一轉換：naive UTC datetime 或 Graph ISO 字串 → Taipei（UTC+8）格式化字串。

    - None／空值 → "—"（模板不用再各自寫 or '—'）。
    - aware datetime 先轉 UTC；naive 一律視為 UTC（B2：DB 只存 naive UTC）。
    - ISO 字串容忍尾碼 Z 與超過 6 位的小數秒（Graph 常見 7 位）。
    - 無法解析的字串原樣回傳——顯示 filter 不得讓整頁 500，寧可露出原始值供排查。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return "—"
    if isinstance(value, str):
        text = value.strip()
        iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
        match = _FRACTION.search(iso)
        if match:
            iso = iso[: match.start()] + "." + match.group(1)[:6] + iso[match.end():]
        try:
            value = datetime.fromisoformat(iso)
        except ValueError:
            return text
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return (value + _TAIPEI_OFFSET).strftime(fmt)
