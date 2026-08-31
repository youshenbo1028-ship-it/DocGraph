"""窗口控制自动化（修复验证）：WindowApi 使用模块级 _window，不依赖 pywebview 注入 self.window。"""

from __future__ import annotations

import app.main as main


class FakeWindow:
    """最小窗口模拟：记录 minimize/maximize/restore/destroy 调用。"""

    def __init__(self) -> None:
        self.minimized = False
        self.maximized = False
        self.restored = False
        self.destroyed = False

    def minimize(self) -> None:
        self.minimized = True

    def maximize(self) -> None:
        self.maximized = True

    def restore(self) -> None:
        self.restored = True

    def destroy(self) -> None:
        self.destroyed = True


def test_window_controls_call_real_window_methods(monkeypatch):
    w = FakeWindow()
    monkeypatch.setattr(main, "_window", w)
    api = main.WindowApi()

    api.minimize()
    assert w.minimized is True, "minimize 未生效"

    api.toggle_maximize()  # 未最大化 -> maximize
    assert w.maximized is True, "最大化未生效"

    api.toggle_maximize()  # 已最大化 -> restore
    assert w.restored is True, "还原未生效"

    api.close()
    assert w.destroyed is True, "关闭未生效"


def test_window_controls_noop_when_no_window(monkeypatch):
    monkeypatch.setattr(main, "_window", None)
    api = main.WindowApi()
    # _window 为 None 时不应抛错（按钮静默安全）
    api.minimize()
    api.toggle_maximize()
    api.close()


def test_window_controls_no_self_window_dependency():
    """关键：WindowApi 不应再依赖 pywebview 注入的 self.window。"""
    api = main.WindowApi()
    assert not hasattr(api, "window") or api.window is None  # 不依赖 self.window
