# -*- coding: utf-8 -*-
"""
数据库连接环境变量共用加载器。

后端 backend/config.py 与本项目脚本必须读同一份配置，否则会出现
"后端连的是 .env 里的库、init_db 建到了默认口令的库" 这类难查的不一致。
查找顺序：进程环境变量 > data-generator/.env > 仓库根 .env（先命中者生效）。
"""

from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)


def load_dotenv() -> int:
    """极简 .env 加载（不引依赖）：KEY=VALUE、# 注释、引号可选；不覆盖已有环境变量"""
    for path in (os.path.join(BASE_DIR, ".env"), os.path.join(ROOT_DIR, ".env")):
        if not os.path.isfile(path):
            continue
        loaded = 0
        with open(path, "r", encoding="utf-8") as f:
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
