# DocGraph 技术笔记：pywebview Windows 无边框窗口拖拽

> 记录一次重要排查（2026 秋）："拖动画布/节点时整窗被拖动 / 无法拖动窗口"问题的根因与解法。
> 结论**非常重要**，后续改窗口/拖拽逻辑务必先读本节。

## 结论（一句话）
**pywebview 在 Windows（winforms + edgechromium/WebView2）平台，既不实现 `easy_drag`，也不实现 `-webkit-app-region` 拖拽区，甚至 Win32 `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION)` 也无效。** 无边框（frameless）只是把窗体设成 `FormBorderStyle.None`，没有把 CSS 拖拽区或 HTCAPTION 转发成窗口拖动。

## 证据（源码核查 + 实测）
- 源码：`.venv/lib/site-packages/webview/platforms/`
  - `cocoa.py` / `gtk.py` / `qt.py` / `mshtml.py`：**有** `easy_drag` 实现；
  - `edgechromium.py` / `winforms.py`（Windows）：**无** `easy_drag`、无 frameless 拖拽处理（仅 `FormBorderStyle.None`）。
- 实测（受控 pywebview 窗口）：
  - `SendMessage(WM_NCLBUTTONDOWN=0xA1, HTCAPTION=2)` + 左键按下 + 移动鼠标：**窗口不移动**（WinForms WndProc 拦截）。
  - **`GetCursorPos + SetWindowPos` 程序化移动：窗口确实移动** ✅。

## 三种状态实测
| 配置 | 画布平移/拖节点 | 工具栏拖窗口 |
|---|---|---|
| `easy_drag=True` + 内容 `no-drag` | ❌ | ✅ |
| `easy_drag=False` + `-webkit-app-region: drag` | ✅ | ❌ |
| `easy_drag=False` + **SetWindowPos 程序化跟随光标** | ✅ | ✅ |

## 最终方案（当前实现）
1. `app/main.py` `WindowApi`：
   - `start_move()`：记录按下时光标相对窗口左上角偏移；
   - `move_window()`：`GetCursorPos` → `SetWindowPos(hwnd, cursor-偏移, SWP_NOSIZE|SWP_NOZORDER)` 跟随光标；
   - `end_move()`：清状态。
2. 前端：工具栏 `mousedown`（非交互元素）→ `start_move()` + ~60fps 轮询 `move_window()`；document `mouseup` → `end_move()`。
3. 画布/节点走正常鼠标事件，不受影响。

## 备注 / 待办
- 该方案为 Windows 专用；macOS/Linux 若支持可保留 `-webkit-app-region` 拖拽区。
- 双击工具栏未触发最大化，如需要加 `dblclick -> toggle_maximize`。
- 相关文件：`app/main.py`、`web/src/App.vue`。
