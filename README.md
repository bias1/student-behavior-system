# 高校学生行为数据采集与可视化系统

面向高校学生消费、图书馆进出等行为数据的采集、清洗、分析与大屏可视化系统（本科毕业设计）。
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
python gen_data.py --students 200 --target-consumption 100000 --target-library 50000
python verify_data.py    # 数据质量与索引命中体检（可选）
```

### 3. 启动后端

```powershell
pip install -r backend/requirements.txt
cd backend
python app.py            # http://127.0.0.1:5000 ，浏览器打开 / 可看接口清单
```

### 4. 启动前端

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
| `SECRET_KEY` | student-behavior-dev | Flask 密钥（也是登录 token 签名种子），**生产务必替换为随机串** |
| `APP_ENV` | dev | 置 `prod` 时启动自检对默认凭证升级强告警 |
| `FLASK_DEBUG` | **0** | 置 1 才开启调试与错误回显（本地开发在 `.env` 里写） |
| `CORS_ORIGINS` | `*` | **生产应收敛为前端实际域名** |
| `AUTH_ENABLED` | 1 | 登录守卫开关；0=退化为"仅写接口查 token"的旧演示模式 |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | admin / admin123 | 登录账号；默认口令仅限本地，公网必改 |
| `AUTH_PASSWORD_HASH` | 空 | 推荐只配哈希（生成命令见下），配置后明文凭据失效 |
| `AUTH_TOKEN_TTL` | 43200 | 登录态有效期（秒），默认 12 小时 |
| `API_ADMIN_TOKEN` | 空 | 脚本/定时任务旁路凭证（`X-API-Token` 头，免登录） |
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

`tests/` 覆盖跨年自然周边界、连续段计数、簇命名贪心与显著性门槛、
`.env` 加载优先级、登录守卫（匿名 401/口令哈希/伪造 token/旁路 token）、
口令哈希往返、token 过期等最易回归的逻辑。
`smoke_test.py` 自动走 `API_ADMIN_TOKEN` 旁路并额外校验"匿名必须被拦 +
登录接口可拿 token"，无需先手动登录。

---

## 六、安全设计说明

本系统为教学演示项目，数据均为 Faker 生成的**模拟数据**，不含真实个人信息。
安全层面已落实：

- **SQL 注入防护**：所有查询用 SQLAlchemy 命名绑定参数；`dim`/`features`/`order` 等
  枚举走白名单，绝不把用户输入拼进 SQL 或当列名。
- **输入校验**：分页/时间窗口参数夹取到合法区间；预警筛选的 `status`/`level`、日期
  非法值显式返回 400 而非 500。
- **凭证外置**：口令/密钥从 `.env` 读取，仓库只提交 `.env.example`；启动时 `security_check()`
  对默认口令、全开 CORS、默认/明文登录口令、关闭守卫输出日志告警（`APP_ENV=prod` 时升级强告警）。
- **登录守卫（轻量，单管理员角色）**：默认开启，除 `/api/health` 与
  `/api/auth/login|status` 外所有接口需 `Authorization: Bearer <token>`；
  前端登录后才可见数据，401 自动跳登录页。实现见 `backend/api/auth.py` +
  `app.py` 的 `_auth_guard`（设计取舍：演示项目不引入完整用户表/JWT 库，
  token 用 itsdangerous 对 `SECRET_KEY` 签名，无状态可过期）。
- **写操作鉴权**：预警扫描/重算/处置同样处于守卫之下；`API_ADMIN_TOKEN` 仅作
  脚本/定时任务的旁路凭证，与登录 token 二选一（定长比较防时序探测）。

### 登录口令哈希生成（推荐配置方式）

```powershell
cd backend
python -c "from api.auth import make_password_hash; print(make_password_hash('你的口令'))"
# 把输出粘进 .env 的 AUTH_PASSWORD_HASH，并删掉 AUTH_PASSWORD 行
```

### 部署注意（生产）

- 环境变量：`APP_ENV=prod`、`FLASK_DEBUG=0`、随机 `SECRET_KEY`/`DB_PASSWORD`、
  非默认 `AUTH_PASSWORD_HASH`、`CORS_ORIGINS` 收敛为前端域名、`API_ADMIN_TOKEN` 可留空。
- 前端生产包请求相对路径 `/api`（见 `frontend/.env.production`），由 Nginx 反代到后端；
  **不要**把 `VITE_API_BASE_URL` 写成 `127.0.0.1:5000`（那是用户自己的电脑）：

```nginx
location / {
    try_files $uri $uri/ /index.html;   # history 模式路由兜底
}
location /api/ {
    proxy_pass http://127.0.0.1:5000;   # 同机部署时反代 Flask
    proxy_set_header Host $host;
}
```

- Flask 自带服务器仅供开发；生产用 `gunicorn -w 4 app:app`（注意聚类/特征缓存是
  进程内的，多 worker 下命中率下降，量大再换 Redis）。
- 默认 `admin/admin123` 只保证本地开箱能演示，公网部署必改，改完启动日志里的
  "默认口令"告警消失为准。

### 已知边界（生产化前需补）

- 登录是**单管理员账号的轻量守卫**，不是完整 RBAC：接真实数据前需引入用户表与
  角色中间件，按"辅导员只看所辖学生"做数据行级权限，并补登录/操作审计日志。
- **token 无吊销机制**（无状态签名，到期或改 `SECRET_KEY` 才失效）：改口令后应
  同步轮换 `SECRET_KEY` 使存量 token 全部作废。
- **数据脱敏**：学号、姓名当前明文返回（演示所需）。对接真实数据前，姓名/学号应在
  出口处脱敏，密码类字段用 bcrypt 存储。
- 预警已具备**处置闭环**（标记已处理/已忽略并保留人工痕迹），但真实的"发现→干预→
  跟进"是业务流程，超出系统本身。
- 聚类画像为**群体统计描述**，前端已标注"仅供资助帮扶参考、不构成学生评价"。
