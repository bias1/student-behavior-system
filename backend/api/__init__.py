# -*- coding: utf-8 -*-
"""
接口层包：统一注册蓝图。

各蓝图自带 url_prefix，app.py 只负责 register，避免路由分散难查。
"""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """集中注册（在这里 import 而非模块级，规避循环依赖）"""
    from api.auth import bp as auth_bp
    from api.clustering import bp as clustering_bp
    from api.consumption import bp as consumption_bp
    from api.library import bp as library_bp
    from api.overview import bp as overview_bp
    from api.student import bp as student_bp
    from api.warning import bp as warning_bp

    for bp in (auth_bp, overview_bp, consumption_bp, library_bp, student_bp, clustering_bp, warning_bp):
        app.register_blueprint(bp)
