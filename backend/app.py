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

import threading
import time
from typing import Any, Dict

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from sqlalchemy import text

from api import register_blueprints
from config import get_config, security_check, validate_config
from logging_setup import setup_logging
from models import db
from utils import SafeJSONProvider, fail, ok

_START_TS = time.time()

# 接口清单：给答辩演示和前端联调用，浏览器打开 / 即可看到全部能力
API_DOCS: Dict[str, Any] = {
    "overview": [
        ("GET  /api/overview", "总览指标：学生数/总消费/日均图书馆时长/行为高峰"),
        ("GET  /api/overview/summary", "概览卡片汇总：活跃率/环比(消费·学习·预警·活跃)/每日迷你趋势(sparkline)"),
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
        ("GET  /api/student/list?keyword=&college=&page=1&size=20&with_stats=1", "学生检索分页（with_stats=1 附带待处理预警数/活跃天数）"),
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
        ("GET  /api/clustering/experiment?k=4&features=full&k_min=2&k_max=8&cap=3000",
         "K-Means 可复现算法实验（需 clustering:run）：预处理诊断/选 K/多种子与重采样与跨窗稳定性/特征消融/MiniBatch 对照"),
        ("GET  /api/clustering/iforest?features=full",
         "IsolationForest 独立异常检测实验（需 clustering:run）：仅输出聚合分数分布与离群计数，不导出个人名单/不映射风险"),
        ("说明: features=core 为毕设总纲要求的 4 特征（日均消费/消费频次/日均在馆时长/消费时间标准差）",
         "features=full（默认）额外包含作息、三餐规律、周末留校等 11 个细分特征"),
    ],
    "warning": [
        ("GET  /api/warning/list?status=0&level=2&workflow_state=0&page=1&size=20",
         "预警列表（筛选+分页；可按工作流态/信号类别/核实结论筛，默认排除数据质量问题与重复项）"),
        ("GET  /api/warning/stats", "预警统计（类型/级别/规则/趋势/工作流，与列表同口径筛选）"),
        ("GET  /api/warning/rule-stats", "规则级统计（触发/核实/误报/处理时长/重复/数据缺失比例，不宣称准确率）"),
        ("GET  /api/warning/rules", "阈值规则配置"),
        ("POST /api/warning/refresh?scope=syllabus|extended|all&persist=1",
         "重新计算总纲四大规则预警（先清失效项再重算，persist=0 为实时计算不落库）"),
        ("POST /api/warning/scan", "执行细粒度扩展规则扫描生成预警（幂等）"),
        ("POST /api/warning/<id>/handle", "（兼容旧接口）处置预警 {status:0|1|2}"),
        ("POST /api/warning/<id>/workflow", "人工核实工作流 {action:assign|start|verify|close|reopen|appeal, ...}（需 warning:handle）"),
        ("总纲四大规则: NO_CONSUME 连续无消费 / CONSUME_DROP 本周消费环比下降 / "
         "NO_LIBRARY 连续未进馆 / NIGHT_WEEK_CONSUME 夜间消费频发",
         "预警等级按严重程度浮动；均为待人工核实信号、不推断个人状况（详见 analysis/warning.py）"),
    ],
    "auth": [
        ("GET  /api/auth/status", "登录守卫开关（匿名可访问，前端路由守卫用）"),
        ("POST /api/auth/login", "登录 {username,password} -> 下发 httpOnly 会话 Cookie + CSRF Cookie"),
        ("POST /api/auth/logout", "退出登录（吊销当前会话）"),
        ("GET  /api/auth/me", "依据会话 Cookie 回显当前身份/权限/数据范围"),
        ("说明: 除 /api/health 与登录入口外，所有 /api/* 需有效会话 Cookie；写操作需 X-CSRF-Token 头",
         "已移除 API_ADMIN_TOKEN 旁路；所有查询按用户数据范围过滤，详见 README《登录与权限》"),
    ],
    "import": [
        ("POST /api/import/consumption", "上传消费流水 CSV（multipart form，字段 file；需 import:run）"),
        ("POST /api/import/library", "上传图书馆进出记录 CSV（需 import:run）"),
        ("GET  /api/import/jobs?page=1&size=20&status=", "导入批次列表（仅本人提交）"),
        ("GET  /api/import/jobs/<id>", "导入批次详情（含逐行错误明细前 20 条）"),
        ("说明: 幂等=SHA256(类型+文件字节)，同文件重复上传不二次写入；写入行带 batch_no 可整批回滚",
         "逐行校验（学号存在性/时间/金额/商户类型），分批提交，导入后自动刷新涉及的日统计"),
    ],
    "jobs": [
        ("POST /api/jobs/clustering", "提交异步 K-Means 作业 {k,features,start,end} -> {job_id}（需 job:manage）"),
        ("POST /api/jobs/elbow", "提交异步手肘法作业 {k_min,k_max,features,start,end}（需 job:manage）"),
        ("POST /api/jobs/daily-stats/refresh", "提交 student_daily_stats 刷新作业 {start,end}"),
        ("POST /api/jobs/clustering/experiment", "提交异步 K-Means 算法实验 {k,features,k_min,k_max,cap,windows}（需 job:manage）"),
        ("GET  /api/jobs?page=1&size=20&status=", "作业列表（仅本人提交，分页）"),
        ("GET  /api/jobs/<id>", "轮询作业状态与结果摘要（含算法版本/数据范围/时间窗口，可追溯）"),
        ("POST /api/jobs/<id>/cancel", "取消作业（pending 直接取消，running 置取消标志）"),
        ("说明: 单机 threading 队列单 worker，状态 pending/running/success/failed/cancelled 全落库",
         "进程重启自动恢复（running→failed、pending 重新入队）；结果摘要不含逐学生身份"),
    ],
}


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(env))
    # prod fail-fast：不安全配置直接拒绝启动（非 prod 直接返回）
    validate_config(app.config)
    # 结构化日志 + 请求追踪钩子：尽早注册（其 before_request 须在认证守卫之前，
    # 保证即使 401/500 也带 request_id）；setup_logging 可重复调用不叠加 handler。
    setup_logging(app)

    # 中文不转义成 \uXXXX，便于接口自查与日志阅读
    app.json = SafeJSONProvider(app)
    app.json.ensure_ascii = False
    # 让 /api/overview 与 /api/overview/ 等价，前端少踩斜杠坑
    app.url_map.strict_slashes = False

    db.init_app(app)
    # Cookie 会话需要携带凭证；prod 下 CORS_ORIGINS 必须是明确域名（validate_config 已保证非 *）
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
         supports_credentials=True, max_age=86400)

    register_blueprints(app)
    _register_core_routes(app)
    _register_error_handlers(app)

    # 启动时把不安全配置写成日志告警：只提醒不阻断（本地演示需要默认配置能直接跑），
    # 但公网部署时这几行会持续出现在服务日志里，提醒换掉默认凭证/收敛 CORS/配好登录口令
    for warning in security_check(app.config):
        app.logger.warning("[安全配置] %s", warning)
    _auth_guard(app)

    # 阶段 2：启动单机后台作业 worker（崩溃恢复 + 消费 pending 队列）。
    # 启动失败（如数据库未就绪）只记日志，不阻断建应用；此时异步作业停留在 pending，
    # 下次进程起来会自动重新入队。测试可用 START_WORKER=0 关闭。
    if app.config.get("START_WORKER", True):
        try:
            import tasks

            tasks.start_worker(app)
        except Exception:                                      # noqa: BLE001
            app.logger.exception("[tasks] 后台 worker 启动失败（接口不受影响，作业暂留 pending）")
    return app


def _auth_guard(app: Flask) -> None:
    """
    统一认证/授权/CSRF/请求追踪守卫（阶段 1 生产化，配合 security.py）：
    - 每个请求先生成 request_id（供日志与审计关联），再尽力加载会话；
      命中会话则把身份/权限/数据范围注入 g，供接口与 Scope 下推使用。
    - 除匿名白名单（健康检查/登录入口）外，AUTH_ENABLED 时无有效会话一律 401。
    - 非安全方法（POST/PUT/PATCH/DELETE）强制校验双提交 CSRF 令牌。
    - 已彻底移除 API_ADMIN_TOKEN 旁路（见用户决策）；不存在任何绕过数据范围的服务级 token。
    - AUTH_ENABLED=0 仅供非 prod 离线演示：视为全校授权，prod 下 validate_config 已拦截。
    """
    import hmac

    from security import PERMISSIONS, Scope, load_current_session, resolve_perms, resolve_scope

    _ANON = {"/api/health", "/api/auth/login", "/api/auth/status"}
    _SAFE = {"GET", "HEAD", "OPTIONS"}

    @app.before_request
    def _check_auth():
        # 请求追踪 ID 已由 logging_setup 的 before_request 先行写入 g.request_id，这里直接复用
        path = request.path.rstrip("/") or request.path          # strict_slashes=False，尾斜杠归一
        auth_on = app.config.get("AUTH_ENABLED")

        sess = None
        if auth_on:
            try:
                sess = load_current_session()
            except Exception:                                     # noqa: BLE001  DB 抖动不应 500，按未登录处理
                app.logger.exception("会话加载失败")
                sess = None
        if sess is not None:
            g.current_session = sess
            g.current_user = sess.user
            g.current_perms = resolve_perms(sess.user.id)
            g.current_scope = resolve_scope(sess.user.id)
        elif not auth_on:
            g.current_user = None
            g.current_perms = set(PERMISSIONS)                    # 离线演示：全权限
            g.current_scope = Scope(all=True)                     # 离线演示：全校范围

        if not path.startswith("/api") or path in _ANON:
            return None
        if auth_on and getattr(g, "current_user", None) is None:
            return fail("未登录或登录已过期，请重新登录", 401)
        # CSRF：仅对写操作校验；令牌与会话行绑定，定长比较
        if auth_on and request.method not in _SAFE:
            provided = request.headers.get("X-CSRF-Token", "")
            expected = getattr(g, "current_session").csrf_token
            if not provided or not hmac.compare_digest(provided, expected):
                return fail("CSRF 校验失败，请刷新页面后重试", 403)
        return None


def _register_core_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        """接口清单（答辩时直接在浏览器演示）"""
        return ok({"name": "高校学生行为数据采集与可视化系统", "version": "1.0",
                   "endpoints": API_DOCS})

    @app.get("/api/health")
    def health():
        """健康检查：验证数据库连通性与数据是否就绪。
        匿名访问只报存活；表量/库地址/异常详情仅对已登录会话（守卫生成 g.current_user）
        与调试模式开放，防止公网探测者拿到数据库拓扑。"""
        identified = app.debug or getattr(g, "current_user", None) is not None
        try:
            with db.engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT (SELECT COUNT(*) FROM student) s,"
                    "(SELECT COUNT(*) FROM consumption) c,"
                    "(SELECT COUNT(*) FROM library_record) l,"
                    "(SELECT COUNT(*) FROM warning) w")).mappings().first()
            body = {"status": "up", "uptime_sec": round(time.time() - _START_TS),
                    "request_id": getattr(g, "request_id", "")}
            if identified:
                body["tables"] = dict(row or {})
                body["db"] = f"{app.config['DB_HOST']}:{app.config['DB_PORT']}/{app.config['DB_NAME']}"
            return ok(body)
        except Exception as exc:                                      # noqa: BLE001
            # 数据库不可用时给出可操作的提示，而不是抛 500 让前端猜；
            # 但异常原文可能含主机名/用户名，未认证时只回通用文案
            detail = f"数据库连接失败：{exc}" if identified else "数据库连接失败（详情需认证后查看）"
            return fail(detail, 500, {"status": "down"})


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


app = create_app()


def _warm_stats(flask_app: Flask) -> None:
    """
    启动后在后台预热默认窗口的统计与聚类：万人规模下单条全窗口聚合要 3~12s，
    不预热的话重启后第一个打开首页的人必然先盯 10 秒骨架屏。预热的参数与
    前端首屏完全一致（days=30 被后端钳到全库区间），跑完首屏就是缓存命中。
    失败不影响服务，只慢第一个请求。
    """
    import datetime as dt

    with flask_app.app_context():
        from analysis import clustering, statistics
        from utils import data_range

        t0 = time.time()
        try:
            d_start, d_end = data_range()
            # 与 utils.resolve_window(days=30) 逐字节同口径（字符串窗口才能命中同一缓存 key）
            s30 = max(d_start, d_end - dt.timedelta(days=29)).strftime("%Y-%m-%d")
            e30 = d_end.strftime("%Y-%m-%d")
            statistics.overview()
            statistics.summary_metrics(s30, e30, 30)
            statistics.consumption_trend(s30, e30)
            statistics.consumption_heatmap(s30, e30)
            statistics.consumption_category(s30, e30)
            statistics.library_trend(s30, e30)
            k = int(flask_app.config.get("CLUSTERING_K", 4))
            for fs in ("core", "full"):   # 分群工作台两套特征集 + 个体画像默认 full
                clustering.fit_kmeans(s30, e30, k, feature_set=fs)
                clustering.elbow_curve(s30, e30, feature_set=fs)
            flask_app.logger.info("[预热] 统计与聚类预热完成 %.1fs", time.time() - t0)
        except Exception:
            flask_app.logger.exception("[预热] 失败（不影响服务，首个请求会慢）")


# daemon 线程：随进程退出，不阻塞 app.run
threading.Thread(target=_warm_stats, args=(app,), daemon=True, name="warm-stats").start()


if __name__ == "__main__":
    print(f"[启动] http://{app.config['HOST']}:{app.config['PORT']}  "
          f"数据库 {app.config['DB_NAME']}  调试={app.config['DEBUG']}")
    # threaded=True：大屏会并发请求 5~6 个接口，单线程会被排队拖慢
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"], threaded=True)
