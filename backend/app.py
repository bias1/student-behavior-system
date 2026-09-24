# -*- coding: utf-8 -*-
"""
Flask 后端入口
    开发：python app.py            （或 flask --app app run --debug）
    健康检查：GET /api/health
    接口清单：GET /

说明：建表请使用 database/schema.sql + data-generator/init_db.py，
      不要用 db.create_all()——它无法创建 meal_period / stay_minutes 这两个生成列。
"""

from __future__ import annotations

import time
from typing import Any, Dict

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from sqlalchemy import text

from api import register_blueprints
from config import get_config
from models import db
from utils import SafeJSONProvider, fail, ok

_START_TS = time.time()

# 接口清单：给答辩演示和前端联调用，浏览器打开 / 即可看到全部能力
API_DOCS: Dict[str, Any] = {
    "overview": [
        ("GET  /api/overview", "总览指标：学生数/总消费/日均图书馆时长/行为高峰"),
        ("GET  /api/overview/groups?dim=college", "群体结构对比（college|grade|major|gender）"),
        ("GET  /api/overview/rank?limit=10&order=desc", "消费排行（order=asc 找疑似低消费）"),
        ("GET  /api/overview/meta", "数据时间范围与枚举字典"),
    ],
    "consumption": [
        ("GET  /api/consumption/trend?days=30", "按天消费趋势（含工作日/周末对比）"),
        ("GET  /api/consumption/heatmap?days=30", "星期×小时消费时段热力图"),
        ("GET  /api/consumption/category?days=30", "消费类别占比与 Top 商户"),
    ],
    "library": [
        ("GET  /api/library/trend?days=30", "图书馆人流趋势 + 热力矩阵 + 区域分布"),
        ("GET  /api/library/heatmap", "进馆时段热力图（双高峰）"),
        ("GET  /api/library/hours", "小时边际分布与常去区域"),
    ],
    "student": [
        ("GET  /api/student/list?keyword=&college=&page=1&size=20", "学生检索分页"),
        ("GET  /api/student/<id>/profile?features=full|core",
         "个体画像：KPI/雷达/趋势/餐段/预警/簇标签"),
        ("GET  /api/student/<id>/consumption?page=1", "消费流水明细"),
        ("GET  /api/student/<id>/library?page=1", "进馆记录明细"),
    ],
    "clustering": [
        ("GET  /api/clustering/result?k=4&refresh=0&features=full|core",
         "K-Means 画像聚类：簇中心/逐学生归类/散点坐标/轮廓系数"),
        ("GET  /api/clustering/elbow?k_min=2&k_max=8", "手肘法 SSE 与轮廓系数曲线（K 取值依据）"),
        ("GET  /api/clustering/members?cluster=0", "簇成员明细"),
        ("GET  /api/clustering/table?k=4&features=core", "逐学生归类扁平表（学号+特征值+簇编号+标签）"),
        ("说明: features=core 为毕设总纲要求的 4 特征（日均消费/消费频次/日均在馆时长/消费时间标准差）",
         "features=full（默认）额外包含作息、三餐规律、周末留校等 11 个细分特征"),
    ],
    "warning": [
        ("GET  /api/warning/list?status=0&level=2&page=1&size=20", "预警列表（筛选+分页）"),
        ("GET  /api/warning/stats", "预警统计（类型/级别/规则/趋势）"),
        ("GET  /api/warning/rules", "阈值规则配置"),
        ("POST /api/warning/refresh?scope=syllabus|extended|all&persist=1",
         "重新计算总纲四大规则预警（先清失效项再重算，persist=0 为实时计算不落库）"),
        ("POST /api/warning/scan", "执行细粒度扩展规则扫描生成预警（幂等）"),
        ("POST /api/warning/<id>/handle", "处置预警 {status:1, handled_by:'...'}"),
        ("总纲四大规则: NO_CONSUME 连续无消费 / CONSUME_DROP 本周消费骤降 / "
         "NO_LIBRARY 连续未进馆 / NIGHT_WEEK_CONSUME 夜间消费频发",
         "预警等级按严重程度浮动（详见 analysis/warning.py）"),
    ],
}


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(env))

    # 中文不转义成 \uXXXX，便于接口自查与日志阅读
    app.json = SafeJSONProvider(app)
    app.json.ensure_ascii = False
    # 让 /api/overview 与 /api/overview/ 等价，前端少踩斜杠坑
    app.url_map.strict_slashes = False

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}}, max_age=86400)

    register_blueprints(app)
    _register_core_routes(app)
    _register_error_handlers(app)
    _register_hooks(app)
    return app


def _register_core_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        """接口清单（答辩时直接在浏览器演示）"""
        return ok({"name": "高校学生行为数据采集与可视化系统", "version": "1.0",
                   "endpoints": API_DOCS})

    @app.get("/api/health")
    def health():
        """健康检查：验证数据库连通性与数据是否就绪"""
        try:
            with db.engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT (SELECT COUNT(*) FROM student) s,"
                    "(SELECT COUNT(*) FROM consumption) c,"
                    "(SELECT COUNT(*) FROM library_record) l,"
                    "(SELECT COUNT(*) FROM warning) w")).mappings().first()
            return ok({"status": "up", "uptime_sec": round(time.time() - _START_TS),
                       "tables": dict(row or {}),
                       "db": f"{app.config['DB_HOST']}:{app.config['DB_PORT']}/{app.config['DB_NAME']}"})
        except Exception as exc:                                      # noqa: BLE001
            # 数据库不可用时给出可操作的提示，而不是抛 500 让前端猜
            return fail(f"数据库连接失败：{exc}", 500, {"status": "down"})


def _register_error_handlers(app: Flask) -> None:
    """统一异常出口：任何错误都返回 {code, data, msg}，前端拦截器只需处理一种结构"""

    @app.errorhandler(400)
    def bad_request(e):
        return fail(str(e.description), 400)

    @app.errorhandler(404)
    def not_found(e):
        return fail(f"接口不存在：{request.path}", 404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return fail(f"{request.path} 不支持 {request.method} 方法", 405)

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("服务端异常")
        return fail("服务器内部错误", 500)

    @app.errorhandler(Exception)
    def unhandled(e):
        # HTTPException 交给上面的专用处理器语义，其余才当未预期异常记录堆栈
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return fail(str(e.description), e.code)
        app.logger.exception("未处理异常")
        return fail(f"分析或查询失败：{type(e).__name__}", 500)


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def _t0():
        g.started = time.time()

    @app.after_request
    def _log(resp):
        """开发期打印耗时：大屏接口一旦慢，看日志就能立刻定位是哪个查询"""
        cost = (time.time() - getattr(g, "started", time.time())) * 1000
        if app.debug and request.path.startswith("/api"):
            app.logger.info("%s %s -> %s (%.0fms)", request.method, request.full_path,
                            resp.status_code, cost)
        return resp


app = create_app()


if __name__ == "__main__":
    print(f"[启动] http://{app.config['HOST']}:{app.config['PORT']}  "
          f"数据库 {app.config['DB_NAME']}  调试={app.config['DEBUG']}")
    # threaded=True：大屏会并发请求 5~6 个接口，单线程会被排队拖慢
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"], threaded=True)
