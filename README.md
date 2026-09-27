# 高校学生行为数据采集与可视化系统

面向高校学生消费、图书馆进出等行为数据的采集、清洗、分析与大屏可视化系统（本科毕业设计）。
默认生成 **2000 名学生**、约 50 万条消费记录与 25 万条图书馆记录（可按需调整）。
包含五个页面（前端品牌 **Campus Insight** 深色数据看板）：**群体概览**、**学生列表**、**个体行为画像**、**风险中心**、**分群工作台**；支持 `Ctrl/⌘+K` 命令面板快速跳转与学生检索。

---

## 一、技术栈与模块

| 层 | 技术 | 目录 |
|---|---|---|
| 后端 API | Flask 3 + SQLAlchemy 2 + PyMySQL，端口 `5000` | [`backend/`](backend) |
| 分析层 | pandas / NumPy / scikit-learn（K-Means 聚类、预警引擎、统计） | [`backend/analysis/`](backend/analysis) |
| 前端大屏 | Vue 3 + Vite + ECharts + lucide-vue-next（自研 UI 组件，无第三方组件库），端口 `5173` | [`frontend/`](frontend) |
| 数据库 | MySQL 8（`student_behavior` 库，5 张表） | [`database/schema.sql`](database/schema.sql) |
| 模拟数据 | Faker + NumPy 按行为潜变量生成 | [`data-generator/`](data-generator) |

后端为分层结构：`api/`（蓝图，只做参数解析与响应）→ `analysis/`（纯计算，可单测）→ `models.py`（ORM）。
统一响应体 `{ "code": 200, "data": ..., "msg": "success" }`。

---

## 二、环境要求

- **Python** 3.10+（用到 `str | None` 联合语法）
- **Node.js** 18+
- **MySQL** 8.0（`consumption.meal_period`、`library_record.stay_minutes` 为 STORED 生成列，需 5.7+）

---

## 三、快速开始

> Windows PowerShell 下安装依赖前先执行 `$env:PYTHONUTF8=1`，
> 否则中文注释可能触发 pip 编码错误。

### 1. 配置数据库连接（凭证外置）

复制环境变量模板并按需填写：

```powershell
Copy-Item .env.example .env      # 编辑 .env，至少填 DB_PASSWORD
```

`.env` 已被 `.gitignore` 排除，真实口令不会进仓库。不配置也能跑：
后端会回落到代码默认值（`root / 123456 / student_behavior`），仅适用于本机演示。

### 2. 初始化数据库与模拟数据

```powershell
$env:PYTHONUTF8 = 1
pip install -r data-generator/requirements.txt
cd data-generator
python init_db.py        # 建库建表 + 灌入预警规则（读 ../database/schema.sql）
python gen_data.py --students 2000 --target-consumption 500000 --target-library 250000
python verify_data.py    # 数据质量与索引命中体检（可选）
```

### 3. 应用权限迁移并创建首个管理员

系统**没有内置默认账号/口令**（旧版 `admin/admin123` 与 `API_ADMIN_TOKEN` 旁路已在阶段 1 移除），
必须先建表再创建引导管理员才能登录：

```powershell
pip install -r backend/requirements.txt
cd backend
alembic upgrade head                                          # 建认证/RBAC/会话/审计表 + 种子 4 个角色
python cli_users.py create-admin --username admin --scope-all # 交互式设置口令（≥8 位）
```

> 首次登录、忘记口令重置、角色与数据范围授权见 **§ 六 · 首次登录与账号初始化**。

### 4. 启动后端

```powershell
cd backend
python app.py            # http://127.0.0.1:5000 ，浏览器打开 / 可看接口清单
```

### 5. 启动前端

```powershell
cd frontend
npm install
npm run dev              # http://localhost:5173（已配置代理转发 /api 到后端）
npm run build            # 生产构建输出到 frontend/dist
```

---

## 四、环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` | 127.0.0.1 / 3306 / root / 123456 | MySQL 连接 |
| `DB_NAME` | student_behavior | 库名 |
| `SECRET_KEY` | student-behavior-dev | Flask 密钥（会话/CSRF 签名种子），**生产务必替换为随机串** |
| `APP_ENV` | dev | 置 `prod` 时启动自检对默认凭证升级强告警 |
| `FLASK_DEBUG` | **0** | 置 1 才开启调试与错误回显（本地开发在 `.env` 里写） |
| `CORS_ORIGINS` | `*` | **生产应收敛为前端实际域名** |
| `AUTH_ENABLED` | 1 | 认证开关；0=退化为匿名可浏览的演示模式（仅允许非 prod）|
| `SESSION_TTL` | 28800 | 会话有效期（秒，默认 8h）；会话可吊销，非无状态 token |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_SECONDS` | 5 / 900 | 连续登录失败锁定阈值 / 锁定时长（秒）|
| `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` | admin / 空 | 引导管理员用户名与口令（供 `cli_users.py` / prod 启动校验）|
| `AUDIT_RETENTION_DAYS` / `STATS_MIN_COHORT` | 365 / 5 | 审计保留天数 / 聚合最小群体规模（防小样本反推）|
| `MAX_UPLOAD_BYTES` / `JOB_DEFAULT_TIMEOUT` / `START_WORKER` | 52428800 / 300 / 1 | 导入体积上限 / 作业超时 / 是否起后台 worker |
| `LOG_LEVEL` / `LOG_FORMAT` | INFO / json | 日志级别 / 格式（json\|text）|
| `CLUSTERING_K` / `CLUSTERING_CACHE_TTL` / `ANALYSIS_DEFAULT_DAYS` | 4 / 600 / 30 | 分析参数 |

优先级：**进程环境变量 > `.env` > 代码默认值**。后端 `config.py` 与
`data-generator/db_env.py` 读同一份 `.env`，避免两处口令不一致。

---

## 五、测试

```powershell
cd backend
python -m pytest tests -q        # 分析层核心逻辑 + 安全/登录守卫回归（不依赖数据库）
python smoke_test.py             # 接口冒烟：用 test_client 直连应用，不占端口但需 MySQL 就绪
```

`tests/` 覆盖跨年自然周边界、连续段计数、簇命名贪心与显著性门槛、`.env` 加载优先级、
认证与会话（匿名 401、Cookie 会话签发/校验/吊销、CSRF 双提交、口令哈希往返、登录限流锁定）、
RBAC 权限与数据范围越权、审计、日志脱敏与结构化等最易回归的逻辑。
`smoke_test.py` 用一次性测试账号登录后走通全接口，并校验"匿名必须被拦 + 健康检查 +
`X-Request-Id` 透传"等；需本地 MySQL 就绪（含 Alembic 迁移）。

---

## 六、安全设计说明

本系统为教学演示项目，数据均为 Faker 生成的**模拟数据**，不含真实个人信息。
安全层面已落实：

- **SQL 注入防护**：所有查询用 SQLAlchemy 命名绑定参数；`dim`/`features`/`order` 等
  枚举走白名单，绝不把用户输入拼进 SQL 或当列名。
- **输入校验**：分页/时间窗口参数夹取到合法区间；预警筛选的 `status`/`level`、日期
  非法值显式返回 400 而非 500。
- **凭证外置**：口令/密钥从 `.env` 读取，仓库只提交 `.env.example`；启动时 `security_check()`
  对数据库默认口令/root 账号、默认 `SECRET_KEY`、全开 CORS、关闭认证输出日志告警
  （`APP_ENV=prod` 时由 `validate_config` 升级为**拒绝启动**）。
- **认证会话（httpOnly Cookie + CSRF）**：默认开启，除 `/api/health` 与
  `/api/auth/login|status|me` 外所有 `/api/*` 需有效会话；登录令牌以 `sha256` 存
  `LoginSession` 表、每请求实时查库——**禁用账号/退出/改密/管理员踢出即时生效（可吊销）**。
  非 GET 请求须带 `X-CSRF-Token`（双提交，配可读 Cookie `sb_csrf`）。实现见
  `backend/security.py` + `backend/api/auth.py` + `app.py` 的 `_auth_guard`。
- **RBAC 与数据范围**：接口用 `@require_perm` 声明权限码；角色→权限、用户→数据范围
  （学院/年级/班级/学号/全校）均落库。用户只能看到授权范围内的学生数据，越权返回 403。
- **写操作与审计**：预警扫描/重算/处置、导入、聚类等写操作同样在权限守卫之下，
  统一写 `audit_log`（带 `request_id`，敏感值脱敏）。**已彻底移除 `API_ADMIN_TOKEN` 旁路**。

### 首次登录与账号初始化

系统**没有内置默认账号/口令**。首次使用须先迁移再创建引导管理员（口令以
pbkdf2-sha256 哈希存库，不存明文，也无需手工生成哈希配进 `.env`）：

```powershell
cd backend
alembic upgrade head                                          # 建认证/RBAC/会话/审计表 + 种子角色
python cli_users.py create-admin --username admin --scope-all # 交互式设口令（≥8 位）
```

然后在登录页用该用户名/口令登录。常用运维命令（`python cli_users.py -h` 看全部）：

```powershell
python cli_users.py list                                        # 查看用户/角色/数据范围
python cli_users.py reset-password --username admin             # 忘口令：重置（吊销旧会话+下次强制改密）
python cli_users.py create-user --username li --role counselor  # 建业务账号
python cli_users.py set-scope --username li --type college --value 计算机学院   # 授权数据范围
python cli_users.py grant-role --username li --role analyst     # 追加角色
```

**四个种子角色（按最小权限，职责刻意不重叠）**：

| 角色 | 能看到的菜单 | 定位 |
|---|---|---|
| `system_admin` | 仅"群体概览"（后台可触发扫描/聚类/导入、管用户与审计）| 系统管理，**默认不浏览学生个体明细** |
| `counselor` | 全部五页 | 辅导员：所辖学生的画像/预警核实（需 `set-scope` 授权）|
| `analyst` | 概览 / 风险 / 分群 | 分析员：聚合与脱敏分析，不含个体明细 |
| `auditor` | （无业务菜单）| 审计员：仅查审计 |

> **为什么用管理员登录后只剩"群体概览"一个菜单？** 侧栏按权限过滤，而 `system_admin`
> 刻意不含 `student:read / student:detail / warning:read / clustering:read`（高权限 ≠ 看学生明细）。
> 要看全部页面，请用 `counselor`/`analyst` 账号，或 `grant-role <admin> counselor`
> 后**重新登录**（权限在登录时解析进会话）。

### 部署（生产）

> 完整部署与运维手册见 **[`docs/deployment.md`](docs/deployment.md)**：三套环境（dev/test/prod）、
> Nginx+HTTPS+Gunicorn+最小权限、数据库不暴露公网、备份/恢复/迁移演练、结构化日志与请求追踪、
> 故障恢复流程、上线验收门禁。以下是要点速览。

- **环境切换**：`APP_ENV=prod` 启动自检 `validate_config` 会 **fail-fast**——默认/空 `SECRET_KEY`、
  数据库 `root`/默认口令、`AUTH_ENABLED=0`、`DEBUG`、CORS `*`、会话 Cookie 非 Secure 等
  任一命中即**拒绝启动**，杜绝带不安全配置上线。随机 `SECRET_KEY`、强 `DB_PASSWORD`、
  `CORS_ORIGINS` 收敛为前端域名、MySQL 用最小权限账号 `sb_app`（见 `deploy/mysql_grants.sql`）。
- **拓扑**：公网只开 Nginx 的 443（HTTPS），`/api` 反代到本机 `gunicorn 127.0.0.1:8000`，
  静态前端由 Nginx 直发（SPA `try_files` 回落）；**应用与 MySQL 都不直接暴露公网**。
  配置示例：`deploy/nginx.conf.example`、`backend/gunicorn.conf.py`、
  `deploy/systemd/insight-api.service.example`；可选 `docker-compose.yml`（db 不 publish 3306）。
- **WSGI**：生产用 `gunicorn -c gunicorn.conf.py app:app`（`Linux`，装 `requirements.prod.txt`）。
  ⚠️ **`workers` 默认 1**：阶段 2 的异步作业是进程内 `threading` 队列 + 单 worker 线程，
  多 worker 会在重启时重复入队消费；并发靠 `gthread`（`threads=8`）。横向扩容须先迁作业层到独立 broker。
- **会话/认证**：登录为 httpOnly Cookie（`sb_session`）+ CSRF（`X-CSRF-Token`），可即时吊销；
  RBAC 角色 + 学院/个体数据范围；已**无** `API_ADMIN_TOKEN` 旁路（检测到即拒绝 prod 启动）。
- **备份/恢复演练**：`backend/ops_backup.py`（同实例逻辑备份 + 行数校验）、
  `backend/ops_restore.py`（`list`/`verify`/`restore` 非破坏性恢复演练）；结构变更一律走 Alembic
  迁移，**变更前先命名备份**（详见部署手册 §5、§9）。
- **结构化日志**：一行一条 JSON + `X-Request-Id` 贯穿请求/审计/响应头，
  `SensitiveFilter` 对口令/令牌/Cookie/学号（6~20 位数字）等自动脱敏（`LOG_FORMAT=text` 可回退）。
- **上线门禁**：先用**模拟数据**跑通全链路 + `pytest` 全绿，通过安全/隐私验收，
  再经**授权做数据隔离试点**；**未通过验收前不得声明具备正式生产上线条件**（详见部署手册 §10）。

### 已知边界（生产化前需补）

- 认证/RBAC/可吊销会话/审计日志已在阶段 1 落地（不再是"单管理员轻量守卫"）；
  试点接真实数据时，重点是**按最小权限为每个用户 `set-scope` 授权**，避免默认全校。
- **数据脱敏**：学号、姓名当前明文返回（演示所需）。对接真实数据前，姓名/学号应在
  出口处脱敏，密码类字段用 bcrypt 存储。
- 预警已具备**处置闭环**（标记已处理/已忽略并保留人工痕迹），但真实的"发现→干预→
  跟进"是业务流程，超出系统本身。
- 聚类画像为**群体统计描述**，前端已标注"仅供资助帮扶参考、不构成学生评价"。
