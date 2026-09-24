# -*- coding: utf-8 -*-
"""
Flask 后端配置
连接参数与 data-generator 保持同一套环境变量，避免两处配置不一致。
"""

import os
from urllib.parse import quote_plus

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """默认配置（本地运行）"""

    # ---------------- 数据库 ----------------
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
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

    # ---------------- 分析参数 ----------------
    CLUSTERING_K = int(os.getenv("CLUSTERING_K", "4"))          # K-Means 簇数
    CLUSTERING_CACHE_TTL = int(os.getenv("CLUSTERING_CACHE_TTL", "600"))  # 聚类结果缓存秒数
    ANALYSIS_DEFAULT_DAYS = int(os.getenv("ANALYSIS_DEFAULT_DAYS", "30")) # 默认统计窗口
    WARNING_TOP_N = int(os.getenv("WARNING_TOP_N", "10"))

    # ---------------- 运行 ----------------
    HOST = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_RUN_PORT", "5000"))
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"


class ProdConfig(Config):
    DEBUG = False


config_map = {"dev": Config, "prod": ProdConfig}


def get_config(env: str | None = None) -> type[Config]:
    return config_map.get((env or os.getenv("APP_ENV", "dev")).lower(), Config)
