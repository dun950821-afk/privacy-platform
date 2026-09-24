# App个人信息保护检测与治理平台

面向移动 App 的个人信息保护合规检测与治理平台:支持 App 上传、静态/动态检测引擎接入、合规规则引擎、风险发现与整改复测、检测报告生成,以及 SDK 隐私知识库管理。

---

## 目录

1. [系统架构](#1-系统架构)
2. [技术栈](#2-技术栈)
3. [目录结构](#3-目录结构)
4. [开发环境启动(本地)](#4-开发环境启动本地)
5. [数据库说明(重要)](#5-数据库说明重要)
6. [关联规则(平台风险结论)](#6-关联规则平台风险结论)
7. [生产部署(Docker Compose)](#7-生产部署docker-compose)
8. [常见问题排查](#8-常见问题排查)
9. [默认账号与端口](#9-默认账号与端口)
10. [详细设计文档](#10-详细设计文档)

---

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    访问层 (Browser/CDN)                       │
├─────────────────────────────────────────────────────────────┤
│  前端 SPA (Vue3 + Element Plus + Tailwind + ECharts)          │
│  浅色企业SaaS风 · 白底蓝灰 + 程式蓝点缀                        │
├─────────────────────────────────────────────────────────────┤
│                    API Gateway (Nginx)                       │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│  业务API服务  │  任务编排服务  │  WebSocket   │  Agent通信服务   │
│  (FastAPI)   │  (FastAPI)   │  (FastAPI)   │  (FastAPI)     │
├──────────────┴──────────────┴──────────────┴─────────────────┤
│                     核心服务层                                │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────────┐   │
│  │项目管理 │ │任务调度 │ │规则引擎 │ │证据中心          │   │
│  │服务     │ │服务     │ │服务     │ │服务              │   │
│  └─────────┘ └─────────┘ └─────────┘ └──────────────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────────┐   │
│  │SDK知识库│ │报告服务  │ │整改复测 │ │认证授权服务      │   │
│  │服务     │ │         │ │         │ │                  │   │
│  └─────────┘ └─────────┘ └─────────┘ └──────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                     检测执行层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │静态检测Worker │  │动态检测Agent │  │Agent设备管理     │   │
│  │(Python)      │  │(Python)     │  │                  │   │
│  │MobSF适配器   │  │Frida Hook   │  │ ADB设备池        │   │
│  │AppShark适配器│  │mitmproxy    │  │                  │   │
│  │JADX适配器    │  │UIAutomator2 │  │                  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                     基础设施层                               │
│  PostgreSQL   Redis   本地文件存储      Prometheus/Grafana   │
│  (业务+事件)  (队列+  (证据APK/报文/    (监控)              │
│               缓存)    截图/报告)                            │
└─────────────────────────────────────────────────────────────┘
```

## 2. 技术栈

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | Vue 3 + TypeScript + Vite | SPA |
| UI 框架 | Element Plus + Tailwind CSS | 浅色企业 SaaS 主题 |
| 图表 | ECharts | 风险看板 / 数据流图 |
| 后端框架 | FastAPI (Python 3.11+) | 异步 API |
| ORM | SQLAlchemy 2.0 + Alembic | 数据库迁移 |
| 任务队列 | Redis Streams | 任务调度 |
| 数据库 | PostgreSQL 15+ | 业务主数据 + 事件数据 |
| 缓存 | Redis 7+ | 会话 / 队列 / 设备锁 |
| 对象存储 | 本地文件系统 (MVP) | 证据文件存储 |
| 静态引擎 | MobSF / AppShark / Androguard / JADX | 适配器封装 |
| 动态引擎 | ADB / Frida / mitmproxy / UIAutomator2 | Agent 执行 |
| 部署 | Docker Compose | 生产单机部署 |

## 3. 目录结构

```
privacy-platform/
├── README.md                      # 本文件
├── docs/                          # 设计文档 (01~07)
├── backend/                       # 后端 (FastAPI)
│   ├── app/
│   │   ├── main.py               # FastAPI 入口 (uvicorn app.main:app)
│   │   ├── api/                  # 路由层
│   │   │   ├── v1/               # 业务 API (projects/apps/tasks/findings/...)
│   │   │   ├── agent/            # Agent 通信 API
│   │   │   └── deps.py           # 依赖注入 (鉴权等)
│   │   ├── core/                 # 配置/数据库/安全 (config.py, database.py)
│   │   ├── engine/               # 检测引擎层
│   │   │   ├── base.py           # 引擎基类
│   │   │   ├── adapters/         # MobSF/AppShark/Androguard/JADX 适配器
│   │   │   └── worker.py         # 静态检测 Worker
│   │   ├── models/               # SQLAlchemy 模型 (含 kb.py: privacy_kb/privacy_scan schema)
│   │   ├── schemas/              # Pydantic 模型
│   │   ├── services/             # 业务服务 (report_service, sdk_analysis)
│   │   ├── tasks/                # 任务编排 (orchestrator.py)
│   │   └── seed.py               # 种子数据 (admin 账号、规则、字典)
│   ├── sql/                      # 数据库建表 SQL (privacy_kb/privacy_scan schema)
│   │   └── app_privacy_kb_schema_postgresql.sql
│   ├── init_db.py                # 数据库初始化脚本 (建表 + 种子数据)
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # 后端测试
│   └── requirements.txt          # Python 依赖
├── frontend/                     # 前端 (Vue3 + Vite)
│   ├── src/
│   │   ├── api/                  # Axios API 封装 (按模块)
│   │   ├── views/                # 页面组件 (Dashboard/Workspace/Findings/...)
│   │   ├── components/           # 通用组件
│   │   ├── router/               # 路由
│   │   ├── stores/               # Pinia 状态管理
│   │   └── styles/               # 全局样式
│   ├── vite.config.ts            # Vite 配置 (含 /api 代理到后端)
│   └── package.json
├── agent/                        # 动态检测 Agent (预留)
├── deploy/                       # 生产部署
│   ├── docker-compose.yml        # 一键部署编排
│   └── nginx.conf                # Nginx 反向代理配置
├── scripts/
│   └── start.sh                  # 本地一键启动脚本
└── data/
    ├── evidence/                 # 证据文件存储 (APK/报文/截图/报告)
    └── pgdata/                   # ⚠️ 不要使用!历史遗留的空数据目录 (见 §5)
```

## 4. 开发环境启动(本地)

### 4.1 环境要求

- Python 3.11+ (后端)
- Node.js 18+ (前端)
- PostgreSQL 15+ (数据库)
- Redis 7+ (缓存/队列)
- JRE 11+ (可选, AppShark 污点分析引擎需要)

### 4.1.1 AppShark 引擎部署(可选)

AppShark 是独立的 Java 进程, 不装也能跑 Androguard, 装了才可选 AppShark 引擎:

```bash
sudo mkdir -p /opt/appshark/config/tools/platforms
sudo chown -R $USER:$USER /opt/appshark

# 1. 下载引擎 jar (要求 JRE 11+)
curl -L -o /opt/appshark/AppShark-0.1.2-all.jar \
  https://github.com/bytedance/appshark/releases/download/v0.1.2/AppShark-0.1.2-all.jar

# 2. 引擎级配置
curl -L -o /opt/appshark/config/EngineConfig.json5 \
  https://raw.githubusercontent.com/bytedance/appshark/main/config/EngineConfig.json5

# 3. Android 平台库 (soot 分析需要, 固定放在 <工作目录>/config/tools/platforms 下,
#    按 APK targetSdk 准备对应版本; 取自 Android SDK 官方源)
curl -L -o /tmp/platform-31.zip https://dl.google.com/android/repository/platform-31_r01.zip
# 解压后把 android.jar 放到 /opt/appshark/config/tools/platforms/android-31/android.jar
```

> 注意: AppShark 0.1.2 的 config.json5 不支持 `sdkPath` 键(文档与发行版不一致),
> 平台库只会从 `<工作目录>/config/tools/platforms` 加载; 且进程崩溃时退出码仍为 0,
> 适配器会检查输出与日志中的异常来判断真实结果。

隐私合规规则集在 `backend/appshark/rules/`(已纳入版本管理), 可通过环境变量
`APPSHARK_JAR` / `APPSHARK_HOME` / `APPSHARK_JAVA` / `APPSHARK_RULE_DIR` / `APPSHARK_SDK_PATH` 覆盖默认路径。
适配器环境校验通过后, 创建检测任务时即可勾选 AppShark 引擎。


### 4.2 首次准备

```bash
# 1. 后端依赖 (建议使用虚拟环境)
python3 -m venv /tmp/venv
/tmp/venv/bin/pip install -r backend/requirements.txt

# 2. 前端依赖
cd frontend && npm install
```

### 4.3 启动 PostgreSQL(最重要的一步)

**⚠️ 请勿用 `initdb` 新建数据目录!** 本机的 PostgreSQL 数据目录是:

```
/var/lib/pgsql/data
```

这是系统安装 PostgreSQL 时初始化的目录,里面保存了所有业务数据(项目、App、检测任务、证据、用户等)。**新建数据目录会导致服务连到空库,页面上所有历史数据"消失"。**

启动方式(数据目录属主为 postgres 用户,需要 sudo):

```bash
# 检查是否已运行
pg_isready -h localhost -p 5432

# 未运行时启动
sudo -u postgres pg_ctl -D /var/lib/pgsql/data -l /var/lib/pgsql/pg.log start
```

> 若报错 `could not open lock file "/var/run/postgresql/...": Permission denied`,说明 socket 目录权限不对,可用 `-o "-k /tmp"` 指定 socket 目录:
> ```bash
> sudo -u postgres pg_ctl -D /var/lib/pgsql/data -l /var/lib/pgsql/pg.log -o "-k /tmp" start
> ```
> 同时确认无残留的 `/tmp/.s.PGSQL.*` 文件(若存在且属主为 postgres,先 `sudo rm -f` 再启动)。

### 4.4 启动 Redis

```bash
redis-server --daemonize yes --port 6379 --save "" --appendonly no
redis-cli ping   # 应返回 PONG
```

### 4.5 启动后端 (FastAPI, 端口 8000)

```bash
cd backend
/tmp/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

验证:`curl http://localhost:8000/health` 应返回 `{"status":"ok","version":"1.0.0"}`

### 4.6 启动前端 (Vite, 端口 5173)

```bash
cd frontend
npx vite --host 0.0.0.0 --port 5173
```

前端通过 Vite 代理把 `/api`、`/agent` 请求转发到后端(vite.config.ts)。**注意:代理目标必须写 `http://127.0.0.1:8000` 而不是 `http://localhost:8000`**,否则 Vite 会把 localhost 解析成 IPv6 `::1`,而后端只监听 IPv4,导致页面所有接口报错(见 §8)。

### 4.7 数据库初始化(仅限全新空库)

只有数据库是全新空库时才需要执行。**已有业务数据的库绝不能执行**(会重复建表/种子数据):

```bash
# 1. 创建 schema 和表 (privacy_kb / privacy_scan)
PGPASSWORD=privacy123 psql -h localhost -U privacy -d privacy_platform \
  -f backend/sql/app_privacy_kb_schema_postgresql.sql

# 2. 补充业务表 + 种子数据 (admin 账号、规则、字典)
cd backend && /tmp/venv/bin/python init_db.py
```

### 4.8 一键启动脚本

`scripts/start.sh` 会依次检测并启动 PostgreSQL / Redis / 后端 / 前端:

```bash
VENV=/tmp/venv bash scripts/start.sh
```

> 注意:该脚本会自行启动 PostgreSQL 数据目录(硬编码 `/var/lib/pgsql/data`),若端口已被占用会跳过。

## 5. 数据库说明(重要)

### 5.1 数据目录与账号

| 项目 | 值 |
|------|-----|
| PostgreSQL 数据目录 | `/var/lib/pgsql/data` (系统级,勿动) |
| 数据库 | `privacy_platform` |
| 用户 / 密码 | `privacy` / `privacy123` |
| 连接串 | `postgresql+psycopg2://privacy:privacy123@localhost:5432/privacy_platform` |
| 业务 schema | `public` (项目/任务/检测等业务表) |
| 知识库 schema | `privacy_kb` (SDK/组件/权限/个人信息能力) |
| 扫描结果 schema | `privacy_scan` |

### 5.2 常见误区(血泪教训)

- ❌ **用 `initdb` 新建数据目录** → 服务连到空库,页面数据全部"消失"(数据本身没丢,只是没连上)
- ❌ **普通用户 `ls /var/lib/pgsql/data` 看到"不存在"** → 该目录属主 postgres、权限 700,普通用户无权限读取,需要用 `sudo ls` 或 `sudo -u postgres` 操作
- ❌ **对已有数据的库重复执行 `init_db.py`** → 会重复插入种子数据

### 5.3 数据备份

```bash
# 全量备份(仓库 backup/ 目录下有一份基线备份)
sudo -u postgres pg_dump -h localhost -U privacy privacy_platform | gzip > backup/privacy_platform_$(date +%F).sql.gz

# 从基线备份恢复(全新空库)
sudo -u postgres psql -c "CREATE DATABASE privacy_platform;"
zcat backup/privacy_platform_20260804.sql.gz | sudo -u postgres psql -d privacy_platform
```

## 6. 关联规则(平台风险结论)

关联规则把多个引擎的 Observation(观察事实)组合成一条平台风险结论(Platform Finding)。
规则不是硬编码在代码里,而是存在数据库、可在界面维护、可版本化发布。

### 6.1 规则存储位置

| 项目 | 值 |
|------|-----|
| 存储表 | `rules` + `rule_versions`(复用合规规则表,不另建表) |
| 区分方式 | `rules.category = 'correlation'` |
| 规则内容 | `rule_versions.rule_content`(结构化 JSON:`match` 条件 + `produce` 结论 + `standards`) |
| 生效条件 | `rules.status = 'active'` 且 `rules.current_version_id` 指向已发布版本 |
| 内置规则 | `PRIVACY_CONTACTS_NETWORK`(通讯录信息网络传输),由 `backend/app/services/rule_seed.py` 提供 |

内置规则由种子流程写入:`backend/app/seed.py::seed_database()` 会调用 `seed_correlation_rules(db)`
(幂等,已存在同名 `rule_key` 则跳过)。因此**全新环境执行 §4.7 的 `init_db.py` 后关联规则即生效**,
无需手工插入;已有规则的库重复执行也不会产生重复数据。

管理界面:前端「知识库 → 关联规则」(`/correlation-rules`);接口见 `/api/v1/correlation-rules`。

### 6.2 发布语义(重要)

**保存即新版本,新版本默认不启用**:

- `PUT /api/v1/correlation-rules/{id}/versions` 保存一个新版本后,该规则立即变为 `disabled`
  (`current_version_id` 不指向新版本),关联逻辑随即跳过它 —— 必须显式发布才会生效。
- `POST /api/v1/correlation-rules/{id}/versions/{vid}/publish` 发布指定版本,规则回到 `active`
  并指向该版本。
- `POST /api/v1/correlation-rules/{id}/disable` 停用规则,不会改动历史 Finding。

规则被停用后**不会**产生新的 Platform Finding;已产生的历史 Finding 保留其生成时的
`rule_snapshot`(规则内容快照)与 `correlation_rule_version`,结论可复现,不受后续改规则影响。

### 6.3 预览用法

预览只做「用当前启用版本对某个任务的 Observation 求值」,不在库里写任何数据
(响应中的 `writes` 恒为 `false`,可用它做人工核对):

```bash
# 1. 登录拿 token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["access_token"])')

# 2. 查看内置规则(拿到 id,状态应为 active)
curl -s http://127.0.0.1:8000/api/v1/correlation-rules -H "Authorization: Bearer $TOKEN"

# 3. 预览:某任务是否会命中该规则
curl -s -X POST http://127.0.0.1:8000/api/v1/correlation-rules/<rule_id>/preview \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"task_id": <task_id>}'
```

返回 `would_match`、`matched_observation_ids`、`finding_code`、`existing_findings`、`writes`。

### 6.4 回归测试

规则的正反例 fixture 在 `backend/tests/fixtures/correlation/<rule_key>/{positive,negative}.json`
(目录名对应 `rule_key`;`positive.json` 必须命中,`negative.json` 必须不命中)。新增内置规则时
同步补 fixture:

```bash
cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation_fixtures.py -q
```

关联规则相关用例(校验/求值、种子接线、CRUD 与发布、预览不写库)一并跑:

```bash
cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_rule_evaluator.py tests/test_correlation.py \
  tests/test_correlation_rules_api.py tests/test_correlation_fixtures.py tests/test_finding_auto_trigger.py -q
```

## 7. 生产部署(Docker Compose)

```bash
cd deploy
docker compose up -d --build
```

- PostgreSQL 15 / Redis 7 / 后端 / 前端(nginx) 四个容器
- 前端默认端口 80,Nginx 反向代理 `/api`、`/agent` 到后端 8000
- 数据卷:`pg_data`(数据库)、`evidence_data`(证据文件)
- 首次部署后执行数据库初始化(见 §4.7),生产环境务必修改默认密码

## 8. 常见问题排查

### Q1: 页面一直报错,接口全部失败

检查 Vite 日志是否有 `http proxy error: ... connect ECONNREFUSED ::1:8000`:
- 原因:Vite 代理目标写成 `localhost`,被解析为 IPv6 `::1`,后端只监听 IPv4
- 解决:改 `frontend/vite.config.ts` 代理目标为 `http://127.0.0.1:8000`,重启前端

### Q2: 检测记录/项目/数据"消失"了

- 原因 1:PostgreSQL 被指向了新建的空数据目录(最常见!)
- 排查:`sudo ls /var/lib/pgsql/data` 确认原数据目录存在;`ps aux | grep postgres` 看 `-D` 参数指向哪
- 解决:停掉错误实例,用 §4.3 正确启动 `/var/lib/pgsql/data`
- 原因 2:浏览器连到了别的后端地址(检查 vite 代理与后端实际端口)

### Q3: PostgreSQL 启动失败,`Permission denied`(lock file)

socket 目录不可写或残留旧 socket 文件:
```bash
sudo rm -f /tmp/.s.PGSQL.5432 /tmp/.s.PGSQL.5432.lock   # 清理残留
sudo -u postgres pg_ctl -D /var/lib/pgsql/data -l /var/lib/pgsql/pg.log -o "-k /tmp" start
```

### Q4: 端口被占用

```bash
ss -tlnp | grep -E ":8000|:5173|:5432|:6379"   # 查看占用
```

### Q5: 登录提示账号密码错误

种子数据未初始化:确认执行过 §4.7 的 `init_db.py`(会创建 `admin/admin123`)。

## 9. 默认账号与端口

| 项目 | 地址 / 账号 |
|------|-------------|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 (Swagger) | http://localhost:8000/docs |
| 管理员账号 | admin / admin123 |
| PostgreSQL | localhost:5432 (privacy/privacy123) |
| Redis | localhost:6379 |

## 10. 详细设计文档

见 `docs/` 目录:

- `01-系统架构设计.md` — 总体架构、技术选型、目录结构
- `02-数据库设计.md` — 数据模型、ER 关系
- `03-API接口设计.md` — 接口规范
- `04-前端设计.md` — 前端页面与交互
- `05-引擎适配器设计.md` — 静态/动态检测引擎适配
- `06-Agent通信协议.md` — Agent 与平台通信协议
- `07-安全设计.md` — 安全设计说明
