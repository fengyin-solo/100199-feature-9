"""齿轮箱接口：维护齿轮箱，覆盖确认换油、登记油温异常、更换齿轮箱等动作。

查看类接口对所有登录身份开放（值班管理员可见全部班组，保养人员可看全部但只能改本班组）；
提交类动作由服务层按齿轮箱「所属班组」与当前操作员班组做归属校验，跨班组提交会被挡下。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.identity import TEAMS, Operator, current_operator
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.gearbox import GearboxService

router = APIRouter(prefix="/api/gearbox", tags=["齿轮箱"])

service = GearboxService()

LIST_FIELDS = ["齿轮箱编号", "所属班组", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]
STATUSES = ["待换油", "运行正常", "油温偏高", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按齿轮箱编号检索"),
    status: str | None = Query(default=None, description="待换油、运行正常、油温偏高、已更换"),
    team: str | None = Query(default=None, description="按归属班组过滤：一班、二班、三班"),
    page: int = 1,
    size: int = 20,
    operator: Operator = Depends(current_operator),
) -> PageResult[dict]:
    """按齿轮箱编号、状态、班组过滤齿轮箱列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if team and team not in TEAMS:
        raise HTTPException(status_code=400, detail=f"班组「{team}」不存在，可选：{'、'.join(TEAMS)}")
    items, total = service.list_entries(
        keyword=keyword, status=status, team=team, operator=operator, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats", response_model=dict)
def gearbox_stats(
    team: str | None = Query(default=None, description="按归属班组过滤统计"),
) -> dict[str, int]:
    """齿轮箱页统计；其中「待处理」与换油台账、运营概览同口径。"""
    return service.stats(team=team)


@router.get("/oil-records")
def list_oil_records(
    team: str | None = Query(default=None, description="按台账作业班组（提交时快照）过滤"),
    keyword: str | None = Query(default=None, description="按齿轮箱编号检索"),
    operator: Operator = Depends(current_operator),
) -> dict[str, Any]:
    """换油台账：返回台账明细、条数与待处理数（待处理数与概览一致）。"""
    items, total = service.list_oil_records(team=team, keyword=keyword)
    # 台账筛选了班组时，待处理数也限定该班组；值班管理员不传班组时看全场。
    pending_team = team if team in TEAMS else None
    return {
        "items": items,
        "total": total,
        "pending": service.count_pending(pending_team),
        "viewer": {
            "role": operator.role,
            "team": operator.team,
            "canSubmit": operator.role == "maintainer" and bool(operator.team),
        },
    }


@router.get("/export")
def export_entries(operator: Operator = Depends(current_operator)) -> dict[str, Any]:
    """导出齿轮箱清单：返回当前全部数据（派生字段与列表页同源）。"""
    items, total = service.list_entries(page=1, size=10000, operator=operator)
    return {"module": "gearbox", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int, operator: Operator = Depends(current_operator)) -> dict:
    """读取单条齿轮箱明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id, operator=operator)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"齿轮箱 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条齿轮箱，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="齿轮箱已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    operator: Operator = Depends(current_operator),
) -> ActionResult:
    """对单条齿轮箱执行确认换油、登记油温异常、更换齿轮箱；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
