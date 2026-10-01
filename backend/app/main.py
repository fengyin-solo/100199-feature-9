"""风电场机组运维平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.identity import resolve_user, CurrentUser
from app.routers import ROUTERS
from app.services.gearbox import GearboxService
from app.store import store

app = FastAPI(title="风电场机组运维平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)

gearbox_service = GearboxService()


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/users")
def list_users() -> dict[str, object]:
    """可切换的值班身份清单：供页头选择当前操作人。"""
    return {"items": [dict(row) for row in store.rows("users")]}


@app.get("/api/me")
def me(user: CurrentUser = Depends(resolve_user)) -> dict[str, object]:
    """返回请求头 X-User-Id 对应的当前身份；无法识别时回退为值班管理员。"""
    return user.as_dict()


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。

    齿轮箱待处理数以换油业务口径（状态为「待换油」）为准，
    与换油台账页 /api/gearbox/ledger 的 stats.pending 保持一致。
    """
    data = store.overview()
    for item in data["modules"]:
        if item["name"] == "gearbox":
            item["pending"] = gearbox_service.stats()["pending"]
    for card in data["cards"]:
        if card["label"] == "待处理":
            card["value"] = sum(int(item["pending"]) for item in data["modules"])
    return data
