"""齿轮箱业务规则：班组归属、换油台账、状态流转与统一的待处理口径。

关键口径（页面各处必须一致，不要各写一份）：
- 油品型号 / 上次换油日 / 下次换油日：一律取该齿轮箱「所属班组」在换油台账里
  最近一条换油记录（latest_oil_record）。同一齿轮箱换过多次油时，只认本班组最近一次；
  其他班组留下的记录不覆盖本班组数据。
- 待处理（pending）：状态为「待换油」，或本班组最近一次换油记录的下次换油日已到/逾期。
  换油台账页与运营概览都通过 count_pending 取数，保证两处数字一致。
- 台账里的作业班组/保养人员是提交时的快照：人员调班后，历史记录仍挂在原班组名下。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "gearbox"
OIL_RECORD_MODULE = "gearbox_oil_records"
OIL_ALERT_MODULE = "gearbox_oil_alerts"

REQUIRED_FIELDS = ["齿轮箱编号", "所属机组", "油温上限", "所属班组"]
STATUS_ORDER = ["待换油", "运行正常", "油温偏高", "已更换"]
ACTION_RULES = {"确认换油": "运行正常", "登记油温异常": "油温偏高", "更换齿轮箱": "已更换"}
OIL_CHANGE_ACTIONS = {"确认换油", "登记油温异常"}
DEFAULT_OIL_INTERVAL_DAYS = 180  # 未填下次换油日时，按换油日期顺延半年


def _today() -> date:
    return date.today()


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class GearboxService:
    # ----- 取数与派生口径 -------------------------------------------------

    def _oil_records(self) -> list[dict[str, Any]]:
        return store.rows(OIL_RECORD_MODULE)

    def _alerts(self) -> list[dict[str, Any]]:
        return store.rows(OIL_ALERT_MODULE)

    def latest_oil_record(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """本班组最近一次换油记录：只看齿轮箱所属班组自己的台账，按换油日期倒序。"""
        code = entry.get("齿轮箱编号")
        owner_team = entry.get("所属班组")
        candidates = [
            row for row in self._oil_records()
            if row.get("齿轮箱编号") == code and row.get("作业班组") == owner_team
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda row: (str(row.get("换油日期", "")), int(row.get("id", 0))))

    def is_pending(self, entry: dict[str, Any]) -> bool:
        """待处理：待换油，或本班组最近一次换油记录的下次换油日已到/逾期。更换后不再待处理。"""
        if entry.get("status") == STATUS_ORDER[-1]:
            return False
        if entry.get("status") == "待换油":
            return True
        latest = self.latest_oil_record(entry)
        if latest is None:
            return True
        due = _parse_day(latest.get("下次换油日"))
        return due is not None and due <= _today()

    @staticmethod
    def is_abnormal(entry: dict[str, Any]) -> bool:
        return entry.get("status") == "油温偏高"

    def _decorate(self, entry: dict[str, Any], operator=None) -> dict[str, Any]:
        """补出各页面统一展示的字段；油品型号与换油日期只认本班组最近一次台账。"""
        latest = self.latest_oil_record(entry)
        result = dict(entry)
        result["上次换油日"] = latest.get("换油日期") if latest else None
        result["下次换油日"] = latest.get("下次换油日") if latest else None
        result["油品型号"] = latest.get("油品型号") if latest else None
        result["齿轮箱状态"] = entry.get("status")
        result["pending"] = self.is_pending(entry)
        result["abnormal"] = self.is_abnormal(entry)
        if operator is not None:
            result["可操作"] = operator.can_modify(entry.get("所属班组"))
        return result

    def count_pending(self, team: str | None = None) -> int:
        """换油台账与运营概览共用的待处理口径。"""
        rows = store.rows(MODULE)
        if team:
            rows = [row for row in rows if row.get("所属班组") == team]
        return sum(1 for row in rows if self.is_pending(row))

    # ----- 列表 / 明细 / 统计 ---------------------------------------------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        team: str | None = None,
        operator=None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("齿轮箱编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if team:
            rows = [row for row in rows if row.get("所属班组") == team]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._decorate(row, operator) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int, operator=None) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._decorate(entry, operator) if entry else None

    def stats(self, team: str | None = None) -> dict[str, int]:
        """齿轮箱页与换油台账页的顶部统计；待处理与概览同口径。"""
        rows = store.rows(MODULE)
        if team:
            rows = [row for row in rows if row.get("所属班组") == team]
        month_prefix = _today().isoformat()[:7]
        month_codes = {
            row.get("齿轮箱编号") for row in self._oil_records()
            if str(row.get("换油日期", "")).startswith(month_prefix)
        }
        return {
            "待换油齿轮箱": sum(1 for row in rows if self.is_pending(row)),
            "油温偏高台数": sum(1 for row in rows if self.is_abnormal(row)),
            "本月换油数": sum(1 for row in rows if row.get("齿轮箱编号") in month_codes),
            "待处理": self.count_pending(team),
        }

    def list_oil_records(
        self, *, team: str | None = None, keyword: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """换油台账：按作业班组（快照）或齿轮箱编号筛选；待处理数与概览同口径。"""
        rows = self._oil_records()
        if team:
            rows = [row for row in rows if row.get("作业班组") == team]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("齿轮箱编号", ""))]
        rows = sorted(
            rows, key=lambda row: (str(row.get("换油日期", "")), int(row.get("id", 0))), reverse=True
        )
        return rows, len(rows)

    # ----- 写入 -----------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["振动值"] = values.get("振动值")
        entry["status"] = STATUS_ORDER[0]
        rows.append(entry)
        return self._decorate(entry), []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any], operator
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"齿轮箱 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于齿轮箱可执行范围"

        owner_team = entry.get("所属班组")
        if not operator.can_modify(owner_team):
            # 跨班组提交与管理员代提交统一在这里挡下，并说明原因。
            return None, operator.deny_reason(owner_team)

        if action == "确认换油":
            return self._confirm_oil_change(entry, values, operator)
        if action == "登记油温异常":
            return self._register_oil_alert(entry, values, operator)

        # 更换齿轮箱：同样只有本班组保养人员能执行；历史台账保留不动。
        entry["status"] = ACTION_RULES[action]
        return self._decorate(entry), f"齿轮箱已{action}"

    def _confirm_oil_change(
        self, entry: dict[str, Any], values: dict[str, Any], operator
    ) -> tuple[dict[str, Any] | None, str]:
        oil_brand = str(values.get("油品型号") or "").strip()
        if not oil_brand:
            return None, "请填写本次换油使用的油品型号后再提交"

        change_day = _parse_day(values.get("换油日期")) or _today()
        next_day = _parse_day(values.get("下次换油日"))
        if next_day is None:
            next_day = change_day + timedelta(days=DEFAULT_OIL_INTERVAL_DAYS)
        if next_day <= change_day:
            return None, "下次换油日必须晚于本次换油日期，请核对后重新提交"

        records = self._oil_records()
        record = {
            "id": max((int(row.get("id", 0)) for row in records), default=0) + 1,
            "齿轮箱编号": entry.get("齿轮箱编号"),
            "所属机组": entry.get("所属机组"),
            "换油日期": change_day.isoformat(),
            "油品型号": oil_brand,
            "下次换油日": next_day.isoformat(),
            # 班组与人员取提交时快照：调班后历史仍挂原班组。
            "作业班组": operator.team,
            "保养人员": operator.name or "本班组保养人员",
        }
        records.append(record)
        entry["status"] = "运行正常"
        message = (
            f"{entry.get('齿轮箱编号')} 换油确认已提交（{operator.team}·{record['保养人员']}），"
            f"油品型号 {oil_brand}，下次换油日 {next_day.isoformat()}"
        )
        return self._decorate(entry), message

    def _register_oil_alert(
        self, entry: dict[str, Any], values: dict[str, Any], operator
    ) -> tuple[dict[str, Any] | None, str]:
        alerts = self._alerts()
        alert = {
            "id": max((int(row.get("id", 0)) for row in alerts), default=0) + 1,
            "齿轮箱编号": entry.get("齿轮箱编号"),
            "所属机组": entry.get("所属机组"),
            "登记日期": str(values.get("登记日期") or _today().isoformat()).strip(),
            "油温值": str(values.get("油温值") or "").strip() or "未填写",
            "油温上限": entry.get("油温上限"),
            "登记班组": operator.team,
            "保养人员": operator.name or "本班组保养人员",
            "说明": str(values.get("说明") or "").strip() or "油温超过上限",
        }
        alerts.append(alert)
        entry["status"] = "油温偏高"
        return self._decorate(entry), f"{entry.get('齿轮箱编号')} 油温异常已登记，状态置为「油温偏高」"
