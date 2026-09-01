# DocGraph 技术笔记：pywebview Windows 无边框窗口拖拽

> 记录一次重要排查（2026 秋）："拖动画布/节点时整窗被拖动 / 无法拖动窗口"问题的根因与解法。
> 结论**非常重要**，后续改窗口/拖拽逻辑务必先读本节。

## 结论（一句话）
**pywebview 在 Windows（winforms + edgechromium/WebView2）平台，既不实现 `easy_drag`，也不实现 `-webkit-app-region` 拖拽区。** 无边框（frameless）只是把窗体设成 `FormBorderStyle.None`，没有把 CSS 拖拽区转发成窗口拖动。

## 证据（源码核查）
- `.venv/lib/site-packages/webview/platforms/` 下：
  - `cocoa.py` / `gtk.py` / `qt.py` / `mshtml.py`：**有** `easy_drag` 实现（macOS/Linux/旧IE）；
  - `edgechromium.py`（Windows WebView2）：**没有** `easy_drag`，也没有 frameless 拖拽处理；
  - `winforms.py`：frameless 仅 `self.FormBorderStyle = FormBorderStyle.None`（line 271/558），**无** drag 区/HTCAPTION 逻辑。
- 因此 `easy_drag=True/False` 在 Windows 上是**无效参数**。

## 三种状态实测
| 配置 | 画布平移/拖节点 | 工具栏拖窗口 |
|---|---|---|
| `easy_drag=True` + 内容 `no-drag` | ❌（拖动被窗口拖走/无响应） | ✅ |
| `easy_drag=False` + `-webkit-app-region: drag` | ✅ | ❌（CSS 拖拽区在 Windows 无效） |
| `easy_drag=False` + **Win32 自定义拖拽** | ✅ | ✅ |

## 最终方案（当前实现）
1. `app/main.py`：`WindowApi.start_drag()` —— 用 Win32：
   `ReleaseCapture()` + `SendMessageW(hwnd, WM_NCLBUTTONDOWN=0x00A1, HTCAPTION=2, 0)`，
   让 Windows 系统接管鼠标拖动窗口（`hwnd = window.native.Handle.ToInt32()`）。
2. 前端：工具栏 `mousedown` 时，若目标不是交互元素（button/input/label/…），调用
   `window.pywebview.api.start_drag()`。
3. 画布/节点走正常鼠标事件，不受影响；窗口拖动只在工具栏按下时触发。

## 备注 / 待办
- 该方案为 Windows 专用；macOS/Linux 若未来要支持，可保留 `-webkit-app-region` 拖拽区（cocoa/gtk 支持）。
- 双击工具栏未触发最大化（无原生双击行为），如需要可加 `dblclick -> toggle_maximize`。
- 相关文件：`app/main.py`、`web/src/App.vue`、`web/src/style.css`。
