"""窗口控制自动化（修复验证）：WindowApi 使用模块级 _window，自跟踪最大化状态。"""

from __future__ import annotations

import app.main as main


class FakeWindow:
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
    monkeypatch.setattr(main, "_maximized", False)
    api = main.WindowApi()

    api.minimize()
    assert w.minimized is True

    api.toggle_maximize()  # 未最大化 -> maximize
    assert w.maximized is True
    assert main._maximized is True

    api.toggle_maximize()  # 已最大化 -> restore（自跟踪，不依赖 window.maximized）
    assert w.restored is True
    assert main._maximized is False

    api.close()
    assert w.destroyed is True


def test_window_controls_noop_when_no_window(monkeypatch):
    monkeypatch.setattr(main, "_window", None)
    api = main.WindowApi()
    api.minimize()
    api.toggle_maximize()
    api.close()


def test_window_controls_no_self_window_dependency():
    api = main.WindowApi()
    assert not hasattr(api, "window") or api.window is None
