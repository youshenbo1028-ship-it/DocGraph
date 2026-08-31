"""DocGraph 桌面入口：pywebview 装配（M1 骨架）。

启动方式（开发模式）：
    python -m app.main
"""

from __future__ import annotations


def _frontend_url() -> str:
    # TODO(M1): 开发模式指向 Vite dev server；打包后指向内嵌静态资源（web/dist）
    return "http://127.0.0.1:5173"


def main() -> None:
    import webview

    window = webview.create_window(
        "DocGraph",
        url=_frontend_url(),
        width=1440,
        height=900,
        min_size=(1024, 700),
    )
    # TODO(M1): 注册 JSBridge API（导入/解析/抽取/图谱查询）
    webview.start()


if __name__ == "__main__":
    main()
