"""当前登录身份解析：前端通过请求头带上人员编号，后端据此判定班组归属。

约定：
- X-User-Id：登录人员编号，对应 users 表的 id；
- 未携带或编号无法识别时，回退到值班管理员（对全部班组只读），
  避免未登录态被当作保养人员越权写入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Header

from app.store import store

USERS_MODULE = "users"
ROLE_ADMIN = "admin"
ROLE_MAINTENANCE = "maintenance"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    name: str
    role: str
    team: str | None
    title: str = ""
    note: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "team": self.team,
            "title": self.title,
            "note": self.note,
        }


def _admin() -> CurrentUser:
    for row in store.rows(USERS_MODULE):
        if row.get("role") == ROLE_ADMIN:
            return CurrentUser(
                id=str(row.get("id", "")),
                name=str(row.get("name", "")),
                role=ROLE_ADMIN,
                team=None,
                title=str(row.get("title", "值班管理员")),
                note=str(row.get("note", "")),
            )
    return CurrentUser(id="u0", name="值班管理员", role=ROLE_ADMIN, team=None)


def resolve_user(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> CurrentUser:
    """从 X-User-Id 请求头解析当前人员；解析不出来时按值班管理员只读处理。"""
    if x_user_id:
        for row in store.rows(USERS_MODULE):
            if str(row.get("id", "")) == x_user_id.strip():
                return CurrentUser(
                    id=str(row.get("id", "")),
                    name=str(row.get("name", "")),
                    role=str(row.get("role", "")),
                    team=row.get("team"),
                    title=str(row.get("title", "")),
                    note=str(row.get("note", "")),
                )
    return _admin()
