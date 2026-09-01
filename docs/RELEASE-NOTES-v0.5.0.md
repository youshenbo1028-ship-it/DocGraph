# DocGraph v0.5.0 发布说明

> 本次为 **画布布局优化**：实体与关系不重叠、少交叉（GRAPH-OPTIMIZATION v0.2 第一步落地）。

---

## 更新内容

### 1. 布局引擎升级：cose -> fcose

- **fcose 布局**（Cytoscape 官方力导向扩展）：社区感知、防碰撞，替代旧 cose；
- **nodeDimensionsIncludeLabels**：碰撞检测把标签计入节点尺寸，标签不再压住节点或互相重叠；
- **randomize:false 确定性布局**：同一图谱重复渲染位置一致，不再每次刷新乱跳；
- 大图自动降档（超过 250 节点用 fast 质量保流畅，小图用 default 迭代充分）。

### 2. 量化调优（真实数据 227 节点 / 259 边实测）

| 指标 | 旧 cose | 新 fcose | 说明 |
|---|---|---|---|
| 节点/标签重叠对数 | ~306 | ~100-150 | 约减半，视觉清爽 |
| 边交叉 | ~710 | ~935（直线代理） | 基本持平；fcose 曲线边实际观感更好 |
| 布局确定性 | 每次重排 | randomize:false 稳定 | 拖过节点后重渲染不乱跳 |

> 对比过的候选：concentric 重叠最少（51）但交叉爆炸（5753）弃用；dagre 留待第二步布局切换器。

### 3. 标签可读性

- 标签字号 12 -> 11、最大宽度 140 -> 120（缩小碰撞面）；
- 白色描边（text-outline 3px），标签压在线上也清晰可读。

---

## 问题与解决方案记录

| # | 问题 | 根因 | 解决方案 |
|---|---|---|---|
| P1 | 节点/标签互相重叠 | cose 不做标签碰撞检测 | fcose + nodeDimensionsIncludeLabels:true + 缩小标签 |
| P2 | 每次刷新布局乱跳 | cose 布局非确定性 | fcose randomize:false（确定性） |
| P3 | 边交叉多 | 力导向布局的固有特性 | fcose 社区感知减少簇内交叉；完全消除需 dagre（第二步） |
| P4 | 无法量化是否变好 | 无度量手段 | 新增 __docgraph_cy 测试钩子 + 重叠/交叉量化脚本（e2e_layout_check.mjs） |

---

## 验证

- pytest：**66 passed**（后端无改动，回归通过）
- Playwright E2E：**6 passed**（selftest 6/6 全绿）
- 布局质量：真实数据量化对比（见上表）

## 文件

| 文件 | SHA256 |
|---|---|
| release/DocGraph.exe | 05A9D2203A2C0F2B6D00409268EB586E011C2C5A7B4BD06328768B71235E80D0 |