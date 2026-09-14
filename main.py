"""服务入口：以 uvicorn 启动后端服务（PRD 19.3 交付「可运行后端」）。

用法：``python main.py``（或 ``uvicorn service.api.app:app --port 8000``）。
"""

import uvicorn  # 已声明依赖（pyproject.toml）

from service.api.app import app  # 已装配好的 FastAPI 应用

__all__ = ["main"]

HOST = "0.0.0.0"  # 监听地址：允许本机与局域网访问
PORT = 8000       # 监听端口


def main() -> None:
    """启动服务。"""
    # 步骤 1：交由 uvicorn 承载；应用对象即已装配完成的 app
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
