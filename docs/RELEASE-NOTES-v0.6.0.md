# DocGraph v0.6.0 发布说明

> 本次为**方向变更**：从单文件 exe 转向**本地服务版**——PostgreSQL / Neo4j / Weaviate 本地启动，浏览器访问。

> 架构决策详见 docs/ARCHITECTURE-SERVICE.md。

---

## 变更内容

### 1. 存储层双后端（核心）

- PostgreSQL 服务版：设置 DOCGRAPH_DATABASE_URL 即启用；元库 docgraph_meta 注册项目，每项目一个 docgraph_<pid> 内容库；
- SQLite 便携分支**原样保留**（单文件 exe 继续可用），同一套 SQL 两个后端（适配器翻译 ? 占位符与 rowid）；
- health 接口返回 storage: postgres|sqlite。

### 2. 本地服务编排（Docker Compose）

- docker-compose.yml：postgres:16-alpine / neo4j:5-community / weaviate:1.26，数据落具名卷 + healthcheck；
- scripts/start_service.ps1 一键启动：起服务 -> 迁移数据（幂等）-> 启动后端 -> 自动打开浏览器。

### 3. 数据迁移

- scripts/migrate_sqlite_to_pg.py：既有 SQLite 项目整体迁入 PG（元库 + 每项目库 + 按插入序回填），幂等可重跑；
- 已用真实数据验证：7 个项目迁入 PG，227 节点/259 边完整可查。

### 4. 浏览器访问

- 前端 API 不变，浏览器直接访问 http://127.0.0.1:8765；Playwright 在 PG 模式下验证通过（无控制台错误）。

---

## 验证

- pytest：**69 passed**（66 既有 + 3 个 PG 冒烟，无 PG 环境自动跳过）
- PG 模式端到端：建项目/分组预设/文档/抽取/图谱/详情 全链路通过，中文 UTF-8 完整
- 浏览器 PG 模式：页面渲染 191 节点（默认筛选）、无控制台错误

## 边界与后续

- Neo4j / Weaviate 容器已编排，业务集成属第二/三期（Cypher 查询、向量检索/chat）；
- 本机单用户 127.0.0.1；局域网多人需 0.0.0.0 + 认证（另行立项）；
- 便携 exe 分支继续维护（SQLite）。

---

## 文件

| 文件 | SHA256 |
|---|---|
| release/DocGraph.exe（便携版不变） | 见 v0.5.2 说明 |