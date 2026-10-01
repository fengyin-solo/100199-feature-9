"""齿轮箱业务规则：状态流转、班组归属、换油台账与字段口径都收在这里。

口径约定：
- 换油确认、油温异常登记只能由齿轮箱归属班组的保养人员提交；
  值班管理员可查看全部班组但只读，其他班组只能查看不能改动。
- 换油台账只追加不覆盖，落库时快照班组与操作人；人员调班后历史仍挂原班组。
- 同一齿轮箱换过两次油时，油品型号 / 上次换油日 / 下次换油日一律以台账中
  本班组最近一次「确认换油」为准，列表、明细、导出、概览看到的都是同一份数据。
- 待处理口径全平台统一：齿轮箱当前状态为「待换油」即计入待处理，
  换油台账页与运营概览都从这里取数。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.identity import CurrentUser, ROLE_ADMIN, ROLE_MAINTENANCE
from app.store import store

MODULE = "gearbox"
LEDGER_MODULE = "gearbox_oil_ledger"
REQUIRED_FIELDS = ["齿轮箱编号", "所属机组", "油温上限", "作业班组"]
STATUS_ORDER = ["待换油", "运行正常", "油温偏高", "已更换"]
ACTION_RULES = {"确认换油": "运行正常", "登记油温异常": "油温偏高", "更换齿轮箱": "已更换"}
OIL_ACTIONS = {"确认换油", "登记油温异常"}
# 「更换齿轮箱」属于值班管理员处置权限，不开放给班组提交。
ADMIN_ONLY_ACTIONS = {"更换齿轮箱"}


class GearboxService:
    # ---------- 读取 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("齿轮箱编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._decorate(dict(row)) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._decorate(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["上次换油日"] = ""
        entry["下次换油日"] = ""
        entry["油品型号"] = ""
        entry["pending"] = True
        entry["abnormal"] = False
        entry["齿轮箱状态"] = STATUS_ORDER[0]
        rows.append(entry)
        return dict(entry), []

    # ---------- 换油台账 ----------
    def list_ledger(
        self,
        *,
        gearbox_id: int | None = None,
        action: str | None = None,
    ) -> list[dict[str, Any]]:
        """按登记时间倒序返回台账；台账只追加，倒序后第一条就是最近一次记录。"""
        rows = store.rows(LEDGER_MODULE)
        if gearbox_id is not None:
            rows = [row for row in rows if int(row.get("gearbox_id", 0)) == gearbox_id]
        if action:
            rows = [row for row in rows if row.get("动作") == action]
        return [dict(row) for row in sorted(rows, key=lambda r: int(r.get("id", 0)), reverse=True)]

    def latest_oil_change(self, gearbox_id: int) -> dict[str, Any] | None:
        """同一齿轮箱换过两次油时，取本班组最近一次「确认换油」作为现行口径。"""
        records = [
            row for row in store.rows(LEDGER_MODULE)
            if int(row.get("gearbox_id", 0)) == gearbox_id and row.get("动作") == "确认换油"
        ]
        if not records:
            return None
        return dict(max(records, key=lambda r: int(r.get("id", 0))))

    def stats(self) -> dict[str, int]:
        """换油台账页统计卡片；pending 与运营概览共用同一口径。"""
        month = datetime.now().strftime("%Y-%m")
        rows = store.rows(MODULE)
        return {
            "pending": sum(1 for row in rows if row.get("status") == "待换油"),
            "abnormal": sum(1 for row in rows if row.get("status") == "油温偏高"),
            "month_changed": sum(
                1
                for row in store.rows(LEDGER_MODULE)
                if row.get("动作") == "确认换油" and str(row.get("日期", "")).startswith(month)
            ),
        }

    # ---------- 动作 ----------
    def run_action(
        self,
        entry_id: int,
        action: str,
        user: CurrentUser,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"齿轮箱 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于齿轮箱可执行范围"

        denied = self._deny_reason(entry, action, user)
        if denied:
            return None, denied

        if action == "确认换油":
            return self._confirm_oil_change(entry, user, values)
        if action == "登记油温异常":
            return self._register_abnormal(entry, user, values)
        # 更换齿轮箱（仅值班管理员）
        entry["status"] = ACTION_RULES[action]
        self._sync_flags(entry)
        return self._decorate(dict(entry)), "齿轮箱已更换，状态更新为已更换"

    def _deny_reason(self, entry: dict[str, Any], action: str, user: CurrentUser) -> str:
        """跨班组 / 越权提交一律挡下，并给出可读原因。"""
        if action in ADMIN_ONLY_ACTIONS:
            if user.role != ROLE_ADMIN:
                return "更换齿轮箱属于值班管理员的处置权限，保养人员请联系值班管理员处理"
            return ""
        if action not in OIL_ACTIONS:
            return f"动作「{action}」不属于齿轮箱可执行范围"
        if user.role == ROLE_ADMIN:
            return "值班管理员可查看全部班组的换油数据，但不能代班组提交换油确认与油温异常登记"
        if user.role != ROLE_MAINTENANCE or not user.team:
            return "当前身份不是保养人员，只能查看换油数据，不能提交改动"
        owner = str(entry.get("作业班组") or "")
        if user.team != owner:
            return (
                f"该齿轮箱归属{owner}，{user.team}只能查看不能改动；"
                f"请由{owner}的保养人员提交{action}"
            )
        return ""

    def _confirm_oil_change(
        self, entry: dict[str, Any], user: CurrentUser, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        oil_type = str(values.get("油品型号") or "").strip()
        next_date = str(values.get("下次换油日") or "").strip()
        date = str(values.get("换油日期") or "").strip() or datetime.now().strftime("%Y-%m-%d")
        missing = [name for name, val in (("油品型号", oil_type), ("下次换油日", next_date)) if not val]
        if missing:
            return None, f"确认换油缺少必填信息：{'、'.join(missing)}"
        if not self._is_date(date):
            return None, f"换油日期格式不正确：{date}，应为 YYYY-MM-DD"
        if not self._is_date(next_date):
            return None, f"下次换油日格式不正确：{next_date}，应为 YYYY-MM-DD"
        if next_date < date:
            return None, f"下次换油日 {next_date} 不能早于本次换油日期 {date}"

        record = self._append_ledger(
            entry, user, action="确认换油", date=date, oil_type=oil_type,
            next_date=next_date, note="",
        )
        # 以台账最近一次确认换油为唯一现行口径，回写快照保证各处显示一致。
        entry["上次换油日"] = record["日期"]
        entry["油品型号"] = record["油品型号"]
        entry["下次换油日"] = record["下次换油日"]
        entry["status"] = "运行正常"
        self._sync_flags(entry)
        return self._decorate(dict(entry)), f"换油确认已提交，台账编号 L{record['id']:04d}；现行口径以本次记录为准"

    def _register_abnormal(
        self, entry: dict[str, Any], user: CurrentUser, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        note = str(values.get("异常说明") or "").strip()
        if not note:
            return None, "登记油温异常请填写异常说明（如实测油温与超限情况）"
        date = str(values.get("登记日期") or "").strip() or datetime.now().strftime("%Y-%m-%d")
        if not self._is_date(date):
            return None, f"登记日期格式不正确：{date}，应为 YYYY-MM-DD"

        record = self._append_ledger(
            entry, user, action="登记油温异常", date=date, oil_type="",
            next_date="", note=note,
        )
        entry["status"] = "油温偏高"
        self._sync_flags(entry)
        return self._decorate(dict(entry)), f"油温异常已登记，台账编号 L{record['id']:04d}"

    def _append_ledger(
        self,
        entry: dict[str, Any],
        user: CurrentUser,
        *,
        action: str,
        date: str,
        oil_type: str,
        next_date: str,
        note: str,
    ) -> dict[str, Any]:
        rows = store.rows(LEDGER_MODULE)
        record = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "gearbox_id": int(entry.get("id", 0)),
            "齿轮箱编号": str(entry.get("齿轮箱编号", "")),
            "动作": action,
            "日期": date,
            "油品型号": oil_type,
            "下次换油日": next_date,
            "异常说明": note,
            # 班组与操作人在提交瞬间快照，后续人员调班不影响历史归属。
            "作业班组": str(entry.get("作业班组") or ""),
            "操作人": user.name,
            "登记时间": datetime.now().isoformat(timespec="seconds"),
        }
        rows.append(record)
        return dict(record)

    # ---------- 口径 ----------
    def _decorate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """把台账最近一次换油口径补到齿轮箱上，并同步状态标志，保证各处一致。"""
        self._sync_flags(entry)
        latest = self.latest_oil_change(int(entry.get("id", 0)))
        if latest is not None:
            entry["上次换油日"] = latest["日期"]
            entry["油品型号"] = latest["油品型号"]
            entry["下次换油日"] = latest["下次换油日"]
        return entry

    @staticmethod
    def _sync_flags(entry: dict[str, Any]) -> None:
        status = str(entry.get("status") or "")
        entry["pending"] = status == "待换油"
        entry["abnormal"] = status == "油温偏高"
        entry["齿轮箱状态"] = status

    @staticmethod
    def _is_date(value: str) -> bool:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False
        return True
