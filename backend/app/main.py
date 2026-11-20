"""用户标签画像与行为分析平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.store import store

app = FastAPI(title="用户标签画像与行为分析平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)

# 前端页面按模块名使用下划线路径（/api/funnel_analyze），后端路由使用连字符
# （/api/funnel-analyze）。这里做一次只针对模块名前缀的兼容改写，两种写法都能用。
_MODULE_PATH_ALIASES = {
    f"/api/{name}": f"/api/{name.replace('_', '-')}" for name in store.module_names()
}


@app.middleware("http")
async def _module_path_alias(request, call_next):
    path = request.scope.get("path", "")
    for underscore, hyphen in _MODULE_PATH_ALIASES.items():
        if path == underscore or path.startswith(underscore + "/"):
            request.scope["path"] = hyphen + path[len(underscore):]
            raw = request.scope.get("raw_path")
            if raw:
                request.scope["raw_path"] = hyphen.encode() + raw[len(underscore):]
            break
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
