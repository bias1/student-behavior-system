# -*- coding: utf-8 -*-
"""
Flask 后端配置
连接参数与 data-generator 保持同一套环境变量，避免两处配置不一致。

凭证管理（安全审计后的约定）：
- 敏感值读取优先级：进程环境变量 > backend/.env > 代码默认值；
- .env 已加入 .gitignore，仓库只提交 .env.example 模板；
- 默认口令仅限本地演示，create_app() 里的 security_check() 会在
  生产模式仍使用默认凭证/全开 CORS/写接口未设 token 时输出告警。
"""

import os
from urllib.parse import quote_plus

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)


def load_dotenv(path: str | None = None) -> int:
    """
    极简 .env 加载器（不引入 python-dotenv 依赖）：
    支持 KEY=VALUE、# 注释、值两侧引号；已存在的环境变量不覆盖
    （命令行/系统环境变量优先级最高，便于临时切换库或部署时注入）。
    未指定 path 时依次找 backend/.env 与仓库根 .env（先命中者生效），
    与 data-generator/db_env.py 的查找顺序保持一致。
    """
    paths = [path] if path else [os.path.join(BASE_DIR, ".env"), os.path.join(ROOT_DIR, ".env")]
    for p in paths:
        if not os.path.isfile(p):
            continue
        loaded = 0
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
                    loaded += 1
        return loaded
    return 0


# 先加载 .env 再读配置，下方类属性的 os.getenv 才能拿到文件里的值
load_dotenv()


class Config:
    """默认配置（本地运行）"""

    # ---------------- 数据库 ----------------
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    # 默认值只是本地演示的占位口令；真实口令写进 backend/.env（已 gitignore），
    # 切勿把个人/生产环境的 MySQL 密码提交到仓库
    DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
    DB_NAME = os.getenv("DB_NAME", "student_behavior")

    SECRET_KEY = os.getenv("SECRET_KEY", "student-behavior-dev")

    # 密码需 URL 转义，防止密码里出现 @ : / 等字符导致 URI 解析错误
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 连接池：大屏轮询接口多，预检 + 回收避免 MySQL 8 小时空闲连接被服务端断开
    # 注意参数名是 max_overflow（不是 pool_max_overflow），写错 create_engine 会直接报错
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "max_overflow": 20,
    }

    # ---------------- 跨域 ----------------
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")   # 生产环境应收敛为前端域名

    # ---------------- 接口 ----------------
    API_PREFIX = "/api"
    JSON_SORT_KEYS = False            # 保持趋势数据的日期顺序，不能按 key 排序

    # ---------------- 登录守卫（轻量，非完整 RBAC，见 api/auth.py） ----------------
    # 默认开启：除 /api/health 与 /api/auth/login|status 外，所有 /api/* 必须带
    # Authorization: Bearer <token>。纯离线演示可 AUTH_ENABLED=0 整体关闭。
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "1") == "1"
    # 注意用 `or` 回退而不是 getenv 默认值：.env 里写 AUTH_PASSWORD=（空值）时 getenv
    # 返回空串，若直接拿空串参与比对，compare_digest("", "") 为真，
    # 等于任何人可用空密码登 admin —— 空值一律回退默认口令而不是参与比对
    AUTH_USERNAME = os.getenv("AUTH_USERNAME") or "admin"
    AUTH_PASSWORD = os.getenv("AUTH_PASSWORD") or "admin123"
    AUTH_PASSWORD_HASH = os.getenv("AUTH_PASSWORD_HASH") or ""
    AUTH_TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", "43200"))    # 登录态有效期（秒），默认 12h

    # ---------------- 写操作旁路凭证 ----------------
    # 供冒烟脚本/定时任务使用的服务级 token（X-API-Token 头），与登录 token 二选一即可；
    # AUTH_ENABLED=0 时退化为旧的"仅写接口要求 token"行为。
    API_ADMIN_TOKEN = os.getenv("API_ADMIN_TOKEN", "")

    # ---------------- 分析参数 ----------------
    CLUSTERING_K = int(os.getenv("CLUSTERING_K", "4"))          # K-Means 簇数
    CLUSTERING_CACHE_TTL = int(os.getenv("CLUSTERING_CACHE_TTL", "600"))  # 聚类结果缓存秒数
    ANALYSIS_DEFAULT_DAYS = int(os.getenv("ANALYSIS_DEFAULT_DAYS", "30")) # 默认统计窗口
    WARNING_TOP_N = int(os.getenv("WARNING_TOP_N", "10"))

    # ---------------- 运行 ----------------
    HOST = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_RUN_PORT", "5000"))
    # 调试默认关：裸跑 python app.py 是"安全但少了自动重载"，本地开发在 .env 写 FLASK_DEBUG=1
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    # 环境标识：security_check 用它区分"生产强告警"与"本地演示弱提醒"
    APP_ENV = os.getenv("APP_ENV", "dev")


class ProdConfig(Config):
    APP_ENV = "prod"
    DEBUG = False


config_map = {"dev": Config, "prod": ProdConfig}


def get_config(env: str | None = None) -> type[Config]:
    return config_map.get((env or os.getenv("APP_ENV", "dev")).lower(), Config)


def security_check(cfg) -> list[str]:
    """
    启动时的配置自查，返回告警文本列表（由 app.py 记入日志）。
    只提醒不阻断：本地演示需要默认配置能直接跑起来，
    但 APP_ENV=prod 时每一项默认值都必须换掉，否则告警会在日志里持续可见。
    """
    warns: list[str] = []
    prod = str(cfg.get("APP_ENV", "dev")).lower() == "prod"
    if cfg.get("DB_PASSWORD") == "123456":
        warns.append("数据库使用代码默认口令，请在 backend/.env 中设置 DB_PASSWORD"
                     + ("（生产模式禁止！）" if prod else ""))
    if cfg.get("SECRET_KEY") == "student-behavior-dev":
        warns.append("SECRET_KEY 为默认值，生产环境请通过环境变量覆盖为随机字符串")
    if cfg.get("CORS_ORIGINS") == "*":
        warns.append("CORS 全域名开放，部署时请收敛为前端实际域名")
    if cfg.get("AUTH_ENABLED"):
        if not cfg.get("AUTH_PASSWORD_HASH"):
            if cfg.get("AUTH_PASSWORD") == "admin123":
                warns.append("登录使用默认口令 admin/admin123，公网部署必须改"
                             + ("（生产模式禁止！）" if prod else "")
                             + "；建议用 api.auth.make_password_hash 生成 AUTH_PASSWORD_HASH")
            else:
                warns.append("AUTH_PASSWORD 为明文口令，建议改用 AUTH_PASSWORD_HASH 存哈希")
    else:
        warns.append("AUTH_ENABLED=0：全部读接口匿名可访问，仅适合离线演示；"
                     "至少设置 API_ADMIN_TOKEN 保护写接口")
    return warns
