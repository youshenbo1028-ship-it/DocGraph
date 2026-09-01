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

# 模块级窗口引用：pywebview 不会自动注入 self.window 到 js_api 实例
_window: "webview.Window | None" = None
# 自跟踪最大化状态：pywebview 的 window.maximized 属性在部分版本/无边框窗口下不可靠
_maximized = False


def _start_server() -> None:
    import uvicorn

    from docgraph.server.app import app

    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")


def _frontend_url() -> str:
    from docgraph.server.app import _dist_dir

    if _dist_dir() is not None:
        return f"http://{API_HOST}:{API_PORT}/"
    return FRONTEND_DEV_URL


class WindowApi:
    """暴露给前端的窗口控制接口（前端 window.pywebview.api.*）。"""

    def minimize(self) -> None:
        if _window is not None:
            _window.minimize()

    def toggle_maximize(self) -> None:
        global _maximized
        if _window is None:
            return
        if _maximized:
            _window.restore()
            _maximized = False
        else:
            _window.maximize()
            _maximized = True

    def close(self) -> None:
        if _window is not None:
            _window.destroy()


def main() -> None:
    global _window
    threading.Thread(target=_start_server, daemon=True).start()

    _window = webview.create_window(
        "DocGraph",
        url=_frontend_url(),
        width=1440,
        height=900,
        min_size=(1080, 700),
        frameless=True,
        easy_drag=False,  # 保住画布/节点交互（重要）；窗口移动见自定义拖拽区方案
        js_api=WindowApi(),
    )
    webview.start()


if __name__ == "__main__":
    main()
