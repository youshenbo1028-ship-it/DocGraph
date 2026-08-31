"""DocGraph 桌面入口：内置 API 服务 + pywebview 装配。

- 开发模式：前端由 Vite（5173）提供，后端在 8765；
- 打包模式：web/dist 由后端静态挂载，pywebview 直接打开 http://127.0.0.1:8765/。
"""

from __future__ import annotations

import threading

API_HOST = "127.0.0.1"
API_PORT = 8765
FRONTEND_DEV_URL = "http://127.0.0.1:5173"


def _start_server() -> None:
    import uvicorn

    from docgraph.server.app import app

    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")


def _frontend_url() -> str:
    from docgraph.server.app import _dist_dir

    if _dist_dir() is not None:  # 打包模式：内嵌静态资源由后端服务
        return f"http://{API_HOST}:{API_PORT}/"
    return FRONTEND_DEV_URL


def main() -> None:
    threading.Thread(target=_start_server, daemon=True).start()

    import webview

    webview.create_window(
        "DocGraph",
        url=_frontend_url(),
        width=1440,
        height=900,
        min_size=(1024, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
