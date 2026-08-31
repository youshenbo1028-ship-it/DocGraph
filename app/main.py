"""DocGraph 桌面入口：内置 API 服务 + pywebview 装配（M1）。"""

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
    # TODO(打包): 打包后指向内嵌静态资源（web/dist）
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
