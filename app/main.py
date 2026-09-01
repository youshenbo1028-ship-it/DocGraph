"""DocGraph 桌面入口：内置 API 服务 + pywebview 装配。

- 无边框窗口（frameless）：去掉系统标题栏，顶部由前端自绘标题栏（拖拽移动 + 窗口控制按钮）；
- 开发模式：前端由 Vite（5173）提供，后端在 8765；
- 打包模式：web/dist 由后端静态挂载，pywebview 直接打开 http://127.0.0.1:8765/。
"""

from __future__ import annotations

import ctypes
import threading

import webview


API_HOST = "127.0.0.1"
API_PORT = 8765
FRONTEND_DEV_URL = "http://127.0.0.1:5173"

# 模块级窗口引用：pywebview 不会自动注入 self.window 到 js_api 实例
_window: "webview.Window | None" = None
# 自跟踪最大化状态：pywebview 的 window.maximized 属性在部分版本/无边框窗口下不可靠
_maximized = False
# 自定义窗口拖动状态：记录按下时 光标相对窗口左上角 的偏移 (dx, dy)
_move_offset: "tuple[int, int] | None" = None

_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004


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

    def start_move(self) -> None:
        """开始自定义窗口拖动：记录光标相对窗口左上角的偏移。"""
        global _move_offset
        if _window is None:
            return
        try:
            hwnd = int(_window.native.Handle.ToInt32())
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            r = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            _move_offset = (pt.x - r.left, pt.y - r.top)
        except Exception:
            _move_offset = None

    def move_window(self) -> None:
        """按当前光标位置移动窗口（保持按下时的相对偏移，跟随光标）。"""
        global _move_offset
        if _window is None or _move_offset is None:
            return
        try:
            hwnd = int(_window.native.Handle.ToInt32())
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0,
                pt.x - _move_offset[0],
                pt.y - _move_offset[1],
                0, 0, _SWP_NOSIZE | _SWP_NOZORDER,
            )
        except Exception:
            pass

    def end_move(self) -> None:
        """结束自定义窗口拖动。"""
        global _move_offset
        _move_offset = None


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
