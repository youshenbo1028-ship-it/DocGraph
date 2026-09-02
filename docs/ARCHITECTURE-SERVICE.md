# DocGraph 架构决策记录：本地服务版（v0.6 方向变更）

> 决策：用户拍板——修改发展方向，让 PostgreSQL / Neo4j / Weaviate 作为本地服务启动，通过网页访问。

> 关联：PRD.md / GRAPH-OPTIMIZATION.md / RELEASE-NOTES-v0.6.0.md

---

## 1. 背景与决策

原方案：单文件 exe（PyInstaller）+ pywebview 内嵌窗口 + SQLite 单项目库。
用户提出：企业正式运营通常使用 Neo4j / PostgreSQL / Weaviate，要求本地启动服务、浏览器访问。

**决策**：产品转向「本地服务版」——

```
DocGraph Local Service Edition
├── Docker Compose 一键启动：
│   ├── PostgreSQL 16  ← 主存储（替代 SQLite）：项目/文档/实体/关系/日志
│   ├── Neo4j 5        ← 图引擎：多跳查询/路径/社区分析（第二期接入查询）
│   └── Weaviate       ← 向量检索：语义去重/RAG（第三期随 chat 启用）
├── DocGraph 后端（FastAPI，改连 PostgreSQL，浏览器访问 http://127.0.0.1:8765）
└── 便携分支：单文件 exe + SQLite 继续保留（零安装场景）
```

**落地策略**（避免一次换四样全崩）：
1. **第一期（本次）**：存储层双后端（SQLite / PostgreSQL 同一套 SQL）+ 浏览器访问 + 启动器 + 数据迁移；
2. **第二期**：Neo4j 同步管线 + Cypher 查询接口；
3. **第三期**：Weaviate + 嵌入（随 chat 功能）。

## 2. 存储层设计（双后端，一套 SQL）

src/docgraph/core/store.py 重构为双后端：

| 层 | SQLite（便携，默认） | PostgreSQL（服务版） |
|---|---|---|
| 连接 | 每项目一个 project.db | 元库 docgraph_meta（projects 注册表）+ 每项目一个库 docgraph_<pid>（内容表） |
| 占位符 | ? | 适配器翻译 ? -> %s |
| 插入顺序 | ORDER BY rowid | schema 增加 seq BIGSERIAL，适配器翻译 rowid -> seq |
| 文档副本 | files/ 本地目录 | 同左（文件始终本地） |
| JSON 列 | TEXT（json.dumps） | TEXT（同左，无方言差异） |

- **为什么每项目一个 PG 库**：现有 schema 中 chunks/entities/relations/evidence 无 project_id 列
  （SQLite 时代靠每项目一个文件隔离）。每项目一个 PG 库保持 schema 与 SQL 完全一致，零重构。
- **适配器**：_SqliteDb / _PgDb 同一方法面（execute/executemany/executescript/commit/close），
  业务 SQL 零改动，既有测试在 SQLite 路径原样通过。
- **切换**：设置 DOCGRAPH_DATABASE_URL 即进入 PG 模式；health 接口返回 storage: postgres|sqlite。

## 3. 运维

- docker-compose.yml：postgres:16-alpine / neo4j:5-community / weaviate:1.26，数据落具名卷，含 healthcheck；
- scripts/start_service.ps1：一键启动三服务 -> 迁移数据（幂等）-> 启动后端 -> 打开浏览器；
- scripts/migrate_sqlite_to_pg.py：SQLite 项目 -> PG（元库注册 + 每项目建库 + 按 rowid 顺序回填），幂等可重复；
- 凭据（docker-compose 内）：PG docgraph/docgraph，Neo4j neo4j/docgraph123（本地工具，后续可配环境变量）。

## 4. 已知边界与后续

- **Neo4j / Weaviate 容器已编排，业务集成未做**（第二/三期）；
- 本机单用户（127.0.0.1）；局域网多人需 0.0.0.0 + 认证（另行立项）；
- 前端 API 不变，浏览器直接可用；pywebview 壳仅便携分支保留；
- 测试：SQLite 路径原有用例 + PG 冒烟用例（无 PG 自动跳过）。

## 5. 环境备注（本机）

- Docker Hub 直连超时 -> daemon.json 配置镜像加速 https://docker.m.daocloud.io；
- Docker Desktop 起不来时：wsl --shutdown 后重启 Docker Desktop。