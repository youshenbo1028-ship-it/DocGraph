# DocGraph v0.2.0 — 发布说明

> 本地 windows 单文件 exe（44.9 MB）
> SHA256: `80A60F33EB0DCE141C1D7CB2F6102A48C71D0608532FB874EE689F3A2A8D95DE`

## 本版本内容

- 文档导入（PDF / Word）-> LLM 抽取实体与关系 -> 实体级知识图谱可视化
- 文件分组（每组独立实体/关系类型表）；文档名唯一，跨组复用自动复制重命名
- 新文件增量适应（组内实体对齐）；图谱搜索 / 类型筛选 / 节点拖动
- 实体与关系详情：**来源文档 + 原文依据摘录（含页码）**
- 导出 PNG / SVG / Graph JSON / CSV（节点+边）
- 无边框窗口 + 自绘标题栏（拖拽移动 / 最小化 / 最大化 / 关闭）
- 用户数据持久化（存储于 **%LOCALAPPDATA%\DocGraph**，重启不丢项目与文档）
- API Key 安全存储（Windows 凭据库）；抽取并行化 + LLM 超时

## 使用

1. 下载 `DocGraph.exe`（双击运行；SmartScreen 提示点"更多信息 -> 仍要运行"）
2. 右上角 ⚙ 填入 LLM API 配置（DeepSeek / OpenAI 等 OpenAI 兼容接口）-> 保存配置
3. ＋导入文档（PDF / DOCX）-> 解析并抽取 -> 生成图谱
4. 点实体/关系线查看来源与原文依据；导出图片 / JSON / CSV

## 自动化自测

- 后端 pytest：49 用例通过
- 前端构建：tsc + vite 通过
- Playwright UI 交互：5 用例通过（渲染 / 文档 / 设置 / 导出 / 详情依据）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\selftest.ps1
```

## 已知说明

- exe 未签名，首次运行 SmartScreen 有"更多信息 -> 仍要运行"提示
- LLM 抽取需用户自备 API Key；数据全本地，仅抽取时调用所配 LLM API
