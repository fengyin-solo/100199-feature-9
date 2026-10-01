"""操作员身份与按班组鉴权。

前端通过请求头带上当前身份（演示环境没有登录态，用顶部切换器模拟）：
- X-Operator-Role：admin（值班管理员，全班组只读可见）/ maintainer（保养人员，只能动本班组）
- X-Operator-Team：一班 / 二班 / 三班
- X-Operator-Name：人员姓名，落台账用

鉴权口径：
- 查看（列表、明细、台账、导出）：谁都能看，值班管理员可见全部班组；
- 提交（确认换油、登记油温异常、更换齿轮箱）：仅齿轮箱「所属班组」的保养人员；
  其他班组进来只能看，跨班组提交一律挡下并给出原因。
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import Header

TEAMS = ["一班", "二班", "三班"]
# HTTP 头只允许 ASCII，前端按 team1/team2/team3 传班组编码。
TEAM_CODES = {"team1": "一班", "team2": "二班", "team3": "三班"}
ROLE_ADMIN = "admin"          # 值班管理员：看全部班组，不替班组提交
ROLE_MAINTAINER = "maintainer"  # 保养人员：只动本班组
ROLE_LABELS = {ROLE_ADMIN: "值班管理员", ROLE_MAINTAINER: "保养人员"}


def _normalize_team(raw: str | None) -> str | None:
    if not raw:
        return None
    if raw in TEAM_CODES:
        return TEAM_CODES[raw]
    return raw if raw in TEAMS else None


@dataclass(frozen=True)
class Operator:
    role: str = ROLE_ADMIN
    team: str | None = None
    name: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def can_modify(self, owner_team: str | None) -> bool:
        """该操作员能否改动归属某班组的齿轮箱。值班管理员与其他班组都不行。"""
        return self.role == ROLE_MAINTAINER and bool(self.team) and self.team == owner_team

    def deny_reason(self, owner_team: str | None) -> str:
        """跨班组/越权提交时给页面的说明。"""
        if self.is_admin:
            return "值班管理员仅可查看全部班组台账，换油确认与油温异常登记须由本班组保养人员提交"
        if not self.team:
            return "当前未归属作业班组，无法提交换油作业，请先选择所属班组"
        owner = owner_team or "未指派班组"
        return (
            f"该齿轮箱归属{owner}，您当前在{self.team}，"
            f"跨班组只能查看，换油确认与油温异常登记须由{owner}保养人员提交"
        )


def current_operator(
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
    x_operator_team: str | None = Header(default=None, alias="X-Operator-Team"),
    x_operator_name: str | None = Header(default=None, alias="X-Operator-Name"),
) -> Operator:
    """从请求头解析当前操作员；缺省按值班管理员处理（只看不改，默认安全）。

    姓名是中文，前端用百分号编码后放到 X-Operator-Name。
    """
    role = x_operator_role if x_operator_role in ROLE_LABELS else ROLE_ADMIN
    team = _normalize_team(x_operator_team)
    name = unquote(x_operator_name or "").strip()
    return Operator(role=role, team=team, name=name)
