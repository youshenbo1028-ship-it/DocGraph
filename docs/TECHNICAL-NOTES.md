# DocGraph 技术笔记：pywebview Windows 无边框窗口拖拽（终版）

> 记录一次重要排查（2026 秋）："拖动画布/节点时整窗被拖动 / 无法拖动窗口"问题。
> **本页为最终结论，已实测通过（三项并存：拖窗口 / 拖画布平移 / 拖节点）。**
> 后续改窗口/拖拽逻辑务必先读本节。

---

## 一、最终结论（已实测）
**三项行为同时成立（真实 exe 验证通过）：**
1. 按住**顶部工具栏空白处**拖动 -> **移动窗口**；
2. 拖**图谱空白处** -> **平移视图**；
3. 拖**实体节点** -> **移动该节点**。

实现方式：**easy_drag=False（保住画布/节点交互）+ 前端轮询光标位置 + Python SetWindowPos 程序化移动窗口**。

## 二、为什么之前"跷跷板"，以及为什么这次成功

### 2.1 pywebview 在 Windows 上"拖拽能力缺失"
源码核查（.venv/lib/site-packages/webview/platforms/）：
- easy_drag 只在 **macOS(cocoa) / GTK / Qt / 旧IE(mshtml)** 实现；
- Windows 的 **edgechromium.py（WebView2）与 winforms.py 完全没有** easy_drag，也没有 -webkit-app-region 拖拽区处理；
- frameless 在 Windows 上只是 FormBorderStyle.None（去边框），**不提供任何"用鼠标拖窗口"的能力**。

因此：
- easy_drag=True：虽意图"整窗可拖"，但**画布也被当窗口拖** -> 画布/节点无法交互（实测失败）；
- easy_drag=False：画布/节点交互恢复，但**窗口无任何拖拽能力**（实测失败）；
- 连标准技巧 SendMessage(WM_NCLBUTTONDOWN, HTCAPTION) 也**实测无效**（WinForms 的 WndProc 拦截，左键按下+移动也不动窗口）。

### 2.2 为什么 SetWindowPos 方案成功
**绕开"系统拖动"机制，改为"程序化定位"**：
- 前端在工具栏按下时开始**轮询**（约 60fps），每次把当前光标屏幕坐标发给 Python；
- Python 用 GetCursorPos 取光标，SetWindowPos(hwnd, x, y, SWP_NOSIZE|SWP_NOZORDER) 直接把窗口移到"光标位置 - 按下时偏移"；
- 窗口以**绝对坐标**移动，不依赖 pywebview 的任何拖拽支持，也不依赖鼠标事件在 WebView 内的传递 -> **必然生效**（受控实测 moved=true，真实 exe 三项并存）。

## 三、最终实现（当前代码）

app/main.py 的 WindowApi：
  - start_move(): 记录 GetCursorPos - GetWindowRect(left,top) 的偏移
  - move_window(): GetCursorPos - 偏移 -> SetWindowPos(hwnd, x, y, SWP_NOSIZE|SWP_NOZORDER)
  - end_move(): 清空偏移

web/src/App.vue：
  - 工具栏 mousedown（非交互元素、左键）: winDragging=true; pyweb()?.start_move(); 启动 16ms 轮询 pyweb()?.move_window()
  - document mouseup: winDragging=false; clearTimeout; pyweb()?.end_move()

## 四、关键参数与注意
- create_window(..., frameless=True, easy_drag=False)：easy_drag=False 必须，否则画布交互失效；
- 内容区（.panel/.canvas*/.layout）设 -webkit-app-region: no-drag：无害冗余（Windows 不读它），保留以防跨平台；
- 工具栏 mousedown 需跳过交互元素（button/input/label/dropdown/win-btn/icon-btn），否则点按钮也拖窗口；
- 轮询 16ms（60fps）移动窗口；若性能担忧可降到 30ms。

## 五、遗留 / 可选
- **双击工具栏 = 最大化**：frameless 无系统双击行为，可加 dblclick -> toggle_maximize；
- macOS/Linux 若未来支持，可保留 -webkit-app-region 拖拽区（那些平台实现 easy_drag）；
- 相关文件：app/main.py、web/src/App.vue、web/src/style.css、本文档。
