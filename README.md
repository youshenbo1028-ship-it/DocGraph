# DocGraph

> 把文档拖进去，生成一张知识图谱。
> 本地文档知识图谱生成与可视化工具：**本地优先 · LLM 驱动 · 单文件 exe**

![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.10+-blue)
![status](https://img.shields.io/badge/status-pre--alpha-orange)

DocGraph 将用户拖入的本地文档（论文 / 报告 / 笔记）自动解析为**实体与关系**，一键生成可交互的**实体级知识图谱**，并以 Windows 单文件 exe 提供「打开即用」的桌面体验。

- 产品需求文档：[PRD.md](PRD.md)
- 文档索引：[docs/](docs/)

## 功能（目标，M1 开发中）

- **单文件图构建（M1）**：PDF / Word 导入 -> 解析分块 -> LLM 抽取实体与关系 -> 图谱渲染
- **文件分组（FR-310）**：每组独立配置实体/关系类型表与抽取参数；文档名唯一，跨组复用自动复制重命名
- **新文件增量适应（FR-311）**：新文件加入分组时，组内实体对齐合并不破坏原图
- **图谱交互**：力导向布局、筛选、搜索、下钻、详情（证据 + 置信度）、导出 PNG/SVG/JSON/CSV
- **隐私优先**：数据全本地，仅抽取时调用用户自配的 LLM API（OpenAI 兼容：DeepSeek / OpenAI / 通义 / Kimi 等）

## 快速开始（开发模式）

```bash
# 后端（uv 虚拟环境；清华镜像配置见 .uv.toml）
uv venv --python 3.10
.venv\Scripts\activate
uv pip install -e ".[dev]"

# 前端
cd web
npm install
npm run dev

# 另开终端启动桌面壳（开发模式指向 Vite dev server）
cd ..
python -m app.main
```

> 打包单文件 exe：见 [scripts/](scripts/README.md)。

## 目录结构

```
DocGraph/
+-- app/                    # 主程序入口与 pywebview 装配
+-- src/docgraph/
|   +-- core/               # 项目模型、存储、配置、密钥管理
|   +-- parsers/            # 文档解析器（pdf/docx/md/txt/html），可插件化
|   +-- extractors/         # LLM 抽取器：provider 抽象 + prompt + JSON Schema
|   +-- graph/              # 图谱构建、去重合并、统计
|   +-- server/             # 内置 HTTP 服务（前端 JSBridge 后端）
+-- web/                    # 前端源码（Vue3 + Vite + Cytoscape.js）
+-- tests/                  # pytest + 前端测试
+-- docs/                   # PRD、架构、用户手册
+-- scripts/                # 打包/发布脚本
+-- examples/               # 示例文档与示例项目
+-- .github/                # ISSUE/PR 模板、CI workflows
+-- PRD.md                  # 产品需求文档
+-- LICENSE                 # MIT（宽松许可，公开可商用）
+-- CONTRIBUTING.md
+-- pyproject.toml
+-- .uv.toml                  # uv 配置（清华 PyPI 镜像）
```

## 路线图

- **V1.0 MVP**：单文件（PDF/DOCX）图构建全链路、LLM 抽取、文件分组与组级配置、组内新文件增量对齐、图谱交互与导出、单 exe
- **V1.1**：批量导入、MD/TXT/HTML 多格式、人工校验中心、路径分析、OCR、代码签名、检查更新
- **V2.0**：本地模型接入、Web 版/团队共享、插件系统、图谱对比

详见 [PRD.md](PRD.md#9-版本规划)。

## 许可证

[MIT](LICENSE) — 宽松许可，公开可商用。
