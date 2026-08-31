# 贡献指南（Contributing）

感谢你愿意参与 DocGraph 的开发！

## 开发流程

1. Fork 本仓库并克隆到本地；
2. 创建特性分支：`git checkout -b feat/xxx` 或 `fix/xxx`；
3. 按 [PRD.md](PRD.md) 的需求编号（FR-xxx）实现，并补充测试；
4. 本地通过 `ruff check src tests app` 与 `pytest`；
5. 提交并推送，发起 Pull Request（请使用仓库内模板）。

## 代码规范

- Python 3.10+，类型注解齐全；行宽 ≤ 100；
- 模块 docstring 说明用途，并标注对应的 PRD 需求编号（如 FR-201）；
- 前端使用 TypeScript + Vue 3；
- 所有耗时操作必须可取消并展示进度（PRD 6.3）。

## 需求对齐

- 任何功能改动请先在 PR 描述中说明对应的 PRD 章节 / 需求编号；
- 大特性建议先开 Issue 讨论再动手。

## 提交规范

- 建议格式：`<type>(<scope>): <subject>`，如 `feat(parsers): 实现 PDF 文本提取（FR-201）`；
- type：feat / fix / docs / refactor / test / chore / build。

## 测试

- 后端：`pytest`
- 前端：`cd web && npm test`
