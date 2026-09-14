"""FastAPI 应用装配（PRD 13 章接口要求）。

职责：创建应用、登记统一错误响应、挂载各业务路由与前端静态资源。
统一约定（PRD 13 章）：前缀 ``/api/v1``、统一 Bearer 鉴权、错误响应含
``error_code`` / ``error_message`` / ``trace_id``。
"""

import uuid  # 错误响应的追踪标识
from pathlib import Path

from fastapi import FastAPI, Request  # 应用与请求上下文
from fastapi.responses import JSONResponse  # 统一错误响应

from service.api import (routers_admin, routers_analysis, routers_approval, routers_attachment,
                         routers_auth, routers_document, routers_session)
from service.infrastructure.errors import ServiceError  # 服务层异常 → 统一错误响应

__all__ = ["app"]

API_PREFIX = "/api/v1"  # 统一接口前缀（PRD 13 章）

app = FastAPI(title="财务单据智能风险审核系统", version="0.1.0",
              description="PRD 2.7 财务单据智能风险审核系统 —— 多智能体协同实现")


@app.exception_handler(ServiceError)
async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
    """统一错误响应（PRD 13.10）：error_code / error_message / trace_id。"""
    # 步骤 1：按服务层异常携带的错误码与状态码构造响应，另附 trace_id 便于链路排查
    return JSONResponse(status_code=exc.status_code,
                        content={"error_code": exc.error_code, "error_message": exc.message,
                                 "trace_id": uuid.uuid4().hex, "detail": exc.detail})


@app.get("/api/v1/health", tags=["系统"])
async def health() -> dict:
    """健康检查：确认服务与数据库连接可用。"""
    # 步骤 1：用一条轻量查询确认数据库可达，避免「服务活着但库连不上」的假象
    from service.infrastructure.database import query_one  # noqa: PLC0415
    row = query_one("SELECT COUNT(*) AS tables_count FROM information_schema.tables "
                    "WHERE table_schema = DATABASE()")
    return {"status": "ok", "tables": row["tables_count"] if row else 0}


# 各业务路由统一挂在 /api/v1 下（PRD 13 章）
for _router in (routers_auth.router, routers_document.router, routers_attachment.router,
                routers_session.router, routers_analysis.router, routers_approval.router,
                routers_admin.router):
    app.include_router(_router, prefix=API_PREFIX)

# 前端静态资源：挂载在根路径，API 路由优先匹配故不受影响（PRD 19.3 可运行前端）
_WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
if _WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles  # noqa: PLC0415
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
