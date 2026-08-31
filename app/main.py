"""DocGraph 桌面入口：内置 API 服务 + pywebview 装配。

- 无边框窗口（frameless）：去掉系统标题栏，顶部由前端自绘标题栏（拖拽移动 + 窗口控制按钮）；
- 开发模式：前端由 Vite（5173）提供，后端在 8765；
- 打包模式：web/dist 由后端静态挂载，pywebview 直接打开 http://127.0.0.1:8765/。
"""

from __future__ import annotations

import threading

import webview

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


class WindowApi:
    """暴露给前端的窗口控制接口（前端 window.pywebview.api.*）。

    pywebview 会把当前 window 注入到 api 实例的 self.window 属性。
    """

    def minimize(self) -> None:
        self.window.minimize()

    def toggle_maximize(self) -> None:
        if self.window.maximized:
            self.window.restore()
        else:
            self.window.maximize()

    def close(self) -> None:
        self.window.destroy()


def main() -> None:
    threading.Thread(target=_start_server, daemon=True).start()

    # js_api 传给 create_window；frameless 去掉系统标题栏，由前端自绘
    webview.create_window(
        "DocGraph",
        url=_frontend_url(),
        width=1440,
        height=900,
        min_size=(1080, 700),
        frameless=True,
        js_api=WindowApi(),
    )
    webview.start()


if __name__ == "__main__":
    main()
