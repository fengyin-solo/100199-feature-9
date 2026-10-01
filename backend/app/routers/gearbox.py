"""齿轮箱接口：维护齿轮箱，覆盖确认换油、登记油温异常、更换齿轮箱等动作。

换油确认与油温异常登记按作业班组划清归属，服务端对跨班组提交一律挡下。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.identity import CurrentUser, resolve_user
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.gearbox import GearboxService

router = APIRouter(prefix="/api/gearbox", tags=["齿轮箱"])

service = GearboxService()

LIST_FIELDS = ["齿轮箱编号", "所属机组", "油温上限", "振动值", "作业班组", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]
STATUSES = ["待换油", "运行正常", "油温偏高", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按齿轮箱编号检索"),
    status: str | None = Query(default=None, description="待换油、运行正常、油温偏高、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按齿轮箱编号与状态过滤齿轮箱列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/ledger")
def list_ledger(
    gearbox_id: int | None = Query(default=None, description="只看某台齿轮箱的台账"),
    action: str | None = Query(default=None, description="确认换油、登记油温异常"),
) -> dict[str, Any]:
    """换油台账：按登记时间倒序返回全部确认换油与油温异常记录。"""
    items = service.list_ledger(gearbox_id=gearbox_id, action=action)
    return {"module": "gearbox", "total": len(items), "items": items, "stats": service.stats()}


@router.get("/stats")
def gearbox_stats() -> dict[str, int]:
    """换油待处理统计；与 /api/overview 的齿轮箱待处理数同一口径。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出齿轮箱清单：返回当前过滤条件下的全量数据（字段口径与列表一致）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "gearbox", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条齿轮箱明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
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
    user: CurrentUser = Depends(resolve_user),
) -> ActionResult:
    """对单条齿轮箱执行动作；跨班组提交、管理员代提交会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, user, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
