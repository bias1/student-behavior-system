# -*- coding: utf-8 -*-
"""
接口冒烟测试：用 Flask test_client 直接跑遍所有接口，无需起服务、不占端口。

    python smoke_test.py            # 全部接口
    python smoke_test.py -v         # 打印每个响应的关键字段

作用：改完分析逻辑先跑这个，比手工点前端快得多；也是"系统测试"章节的素材。
"""

from __future__ import annotations

import json
import sys
import uuid

from app import create_app

VERBOSE = "-v" in sys.argv

# (方法, 路径, JSON体, 断言：data 里必须存在的字段)
CASES = [
    ("GET", "/api/health", None, ["status", "tables"]),
    ("GET", "/", None, ["endpoints"]),
    ("GET", "/api/overview", None,
     ["student_count", "total_amount", "avg_daily_study_minutes", "consume_peak_hour"]),
    ("GET", "/api/overview/summary?days=30", None,
     ["window", "student_count", "active_rate", "amount_delta",
      "warning_count", "spark_amount", "spark_library"]),
    ("GET", "/api/overview/meta", None, ["date_start", "date_end", "merchant_types"]),
    ("GET", "/api/overview/groups?dim=college", None, ["items", "dim"]),
    ("GET", "/api/overview/groups?dim=grade", None, ["items"]),
    ("GET", "/api/overview/groups?dim=wrong", None, None),          # 期望 400
    ("GET", "/api/overview/rank?limit=5", None, ["items"]),
    ("GET", "/api/consumption/trend?days=30", None, ["dates", "series", "window"]),
    ("GET", "/api/consumption/heatmap?days=30", None, ["hours", "weekdays", "data", "max_records"]),
    ("GET", "/api/consumption/category?days=30", None, ["by_merchant_type", "by_meal_period"]),
    ("GET", "/api/library/trend?days=30", None, ["dates", "series", "heatmap", "area_dist"]),
    ("GET", "/api/library/heatmap", None, ["hours", "data", "max"]),
    ("GET", "/api/library/hours", None, ["hour_dist"]),
    ("GET", "/api/student/list?size=5", None, ["total", "items"]),
    ("GET", "/api/student/list?size=5&with_stats=1", None, ["total", "items"]),  # with_stats 字段验证
    # 学生不存在 -> 404
    ("GET", "/api/student/__no_such__/profile", None, None),
    ("POST", "/api/warning/scan", {}, ["written", "by_rule", "rules_enabled"]),
    ("POST", "/api/warning/scan", {}, ["written", "by_rule"]),      # 第二次扫描，验证幂等
    # 总纲四大规则：先实时计算不落库（persist=0），再真重算（带失效清理）
    ("POST", "/api/warning/refresh", {"persist": 0},
     ["persisted", "matched", "by_rule", "by_level", "items", "weeks_compared"]),
    ("POST", "/api/warning/refresh", {}, ["written", "by_rule", "by_level", "removed_stale"]),
    ("POST", "/api/warning/refresh", {"scope": "all"}, ["syllabus", "extended", "written"]),
    ("POST", "/api/warning/refresh?scope=wrong", None, None),        # 期望 400
    ("GET", "/api/warning/list?rule_code=CONSUME_DROP&size=5", None, ["items"]),
    ("GET", "/api/warning/list?size=5", None, ["total", "items"]),
    ("GET", "/api/warning/list?status=0&level=2", None, ["items"]),
    ("GET", "/api/warning/stats", None,
     ["total", "by_type", "by_rule", "trend", "by_workflow", "disclaimer"]),
    ("GET", "/api/warning/rules", None, None),                       # 返回 list，无 dict 字段
    # 阶段 4：五态工作流 / 信号类别筛选，规则级统计（均为只读，不改动预警数据）
    ("GET", "/api/warning/list?workflow_state=0&size=5", None, ["items"]),
    ("GET", "/api/warning/list?signal_kind=need_verification&size=5", None, ["items"]),
    ("GET", "/api/warning/list?signal_kind=__bad__", None, None),     # 非法 signal_kind 期望 400
    ("GET", "/api/warning/list?workflow_state=9", None, None),        # 非法工作流态期望 400
    ("GET", "/api/warning/rule-stats", None,
     ["items", "summary.verified_coverage", "accuracy_note", "disclaimer"]),
    # 认证探活入例（匿名白名单）；登录/401 拦截另外在主循环前做前置校验
    ("GET", "/api/auth/status", None, ["enabled"]),
    # 手肘法：默认按总纲要求扫 K=2..8，输出 SSE 曲线
    ("GET", "/api/clustering/elbow?k_min=2&k_max=8", None,
     ["k", "inertia", "sse", "silhouette", "total_ss", "feature_set"]),
    ("GET", "/api/clustering/elbow?k_max=6", None, ["k", "inertia", "silhouette"]),
    ("GET", "/api/clustering/result?k=4", None,
     ["clusters", "points", "silhouette", "features", "sse", "feature_set", "group_mean"]),
    # 总纲要求的 4 特征集（core）：同一套代码只换特征切片，两条路径都要通
    ("GET", "/api/clustering/result?k=4&features=core&refresh=1", None,
     ["clusters", "points", "silhouette", "feature_keys"]),
    ("GET", "/api/clustering/result?k=3&features=core&refresh=1", None, ["clusters"]),
    ("GET", "/api/clustering/members?cluster=0", None, ["items", "total"]),
    ("GET", "/api/clustering/members?cluster=0&features=core", None, ["items", "feature_set"]),
    ("GET", "/api/clustering/table?k=4&features=core&limit=20", None,
     ["columns", "column_labels", "items", "total"]),
    # 阶段 2：导入批次 / 异步作业列表（只读，不提交作业以免产生异步负载与数据残留）
    ("GET", "/api/import/jobs?size=5", None, ["total", "items", "page", "size"]),
    ("GET", "/api/jobs?size=5", None, ["total", "items", "page", "size"]),
    # 阶段 3：可复现算法实验 / IsolationForest 聚合异常实验（只读、子采样、短窗口）
    ("GET", "/api/clustering/experiment?cap=800&k=4&k_min=2&k_max=6&days=30", None,
     ["meta.random_seed", "k_sweep.k", "stability.seed.mean_ari",
      "feature_comparison", "minibatch.runtime_ms", "disclaimer"]),
    ("GET", "/api/clustering/iforest?days=30", None,
     ["aggregate_only", "score_distribution", "outlier_counts", "disclaimer"]),
    ("GET", "/__not_exist", None, None),                            # 期望 404
]


def _has(data, path: str) -> bool:
    """支持 "cluster.desc" 形式的嵌套字段断言，免得不关键字段只有顶层被检到"""
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def _ensure_smoke_user(app):
    """登录守卫生产化后旁路已移除：为冒烟脚本在本地库临时创建一个
    拥有全部角色（4 角色权限并集=全 10 个权限）+ 全校数据范围的专用用户，
    跑完在 finally 里清理（只删自己创建的行，不碰任何现有数据）。"""
    from api.auth import make_password_hash
    from models import SystemUser, UserRole, UserStudentScope, db

    with app.app_context():
        username = f"smoke_{uuid.uuid4().hex[:10]}"
        password = uuid.uuid4().hex          # 随机口令，仅本次登录用，不落任何日志
        u = SystemUser(username=username,
                       password_hash=make_password_hash(password, iterations=1_000),
                       display_name="冒烟测试专用", status=1)
        db.session.add(u)
        db.session.flush()
        for rc in ("system_admin", "counselor", "analyst", "auditor"):
            db.session.add(UserRole(user_id=u.id, role_code=rc))
        # '*' = 显式全校授权，使所有范围过滤均放行，冒烟才能跑遍全量接口
        db.session.add(UserStudentScope(user_id=u.id, scope_type="*", scope_value="*",
                                        granted_by="smoke"))
        db.session.commit()
        return u.id, username, password


def _cleanup_smoke_user(app, uid):
    """删除临时冒烟用户及其会话（先删会话再删用户：roles/scopes 由 ORM 级联）。"""
    try:
        with app.app_context():
            from models import LoginSession, SystemUser, db
            LoginSession.query.filter_by(user_id=uid).delete(synchronize_session=False)
            u = db.session.get(SystemUser, uid)
            if u is not None:
                db.session.delete(u)
            db.session.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 冒烟用户清理失败（不影响结果）：{exc}")


def main() -> int:
    app = create_app()
    client = app.test_client()
    passed = failed = 0
    sid = None

    # 前置校验 1：未登录请求必须被拦（旁路已彻底移除，不能再靠 X-API-Token 绕过）
    headers: dict = {}
    anon = client.get("/api/warning/list")
    if app.config.get("AUTH_ENABLED"):
        ok_guard = anon.status_code == 401
        print(f"[{'PASS' if ok_guard else 'FAIL'}] 守卫：匿名访问 /api/warning/list -> "
              f"{anon.status_code}（期望 401）")
        passed += ok_guard
        failed += not ok_guard
    else:
        print(f"[SKIP] AUTH_ENABLED=0：匿名读放行（离线演示模式），当前 -> {anon.status_code}")

    # 前置校验 2：真实登录拿会话 Cookie（写操作还需 X-CSRF-Token）
    try:
        uid, uname, pwd = _ensure_smoke_user(app)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法创建冒烟用户（数据库/迁移未就绪？）：{type(exc).__name__}: {exc}")
        print("       请先执行 alembic upgrade head 并确认 DB 连接可用，再跑冒烟。")
        return 1
    try:
        lr = client.post("/api/auth/login", json={"username": uname, "password": pwd})
        ok_login = lr.status_code == 200
        if ok_login:
            ck = client.get_cookie("sb_csrf")
            headers = {"X-CSRF-Token": ck.value} if ck else {}
        print(f"[{'PASS' if ok_login else 'FAIL'}] 登录：POST /api/auth/login -> "
              f"{lr.status_code}（期望 200，下发 httpOnly 会话 Cookie）")
        passed += ok_login
        failed += not ok_login
    finally:
        pass

    # 前置校验 3（阶段 6）：响应必须回写 X-Request-Id，合法的 upstream ID 应被原样透传
    rid_in = "smoke-trace-123_x"
    hr = client.get("/api/health", headers={"X-Request-Id": rid_in})
    rid_out = hr.headers.get("X-Request-Id")
    ok_rid = rid_out == rid_in
    print(f"[{'PASS' if ok_rid else 'FAIL'}] 请求追踪：GET /api/health 响应 X-Request-Id 透传 -> "
          f"{rid_out!r}（期望 {rid_in!r}）")
    passed += ok_rid
    failed += not ok_rid

    with app.app_context():
        from models import Student

        first = Student.query.order_by(Student.student_id).first()
        sid = first.student_id if first else "000000000"

    # 个体画像三个接口依赖真实学号，动态补进用例
    cases = list(CASES) + [
        ("GET", f"/api/student/{sid}/profile", None, ["info", "kpi", "radar", "daily", "cluster"]),
        ("GET", f"/api/student/{sid}/profile?features=core", None,
         ["info", "kpi", "radar", "cluster.label", "cluster.desc", "cluster.definition"]),
        ("GET", f"/api/student/{sid}/consumption?size=3", None, ["total", "items"]),
        ("GET", f"/api/student/{sid}/library?size=3", None, ["total", "items"]),
    ]

    print("=" * 92)
    for method, path, body, keys in cases:
        # 特殊用例：把占位学号换成真实学号，保证能测到完整链路
        if "__no_such__" in path:
            expect_http = 404
        elif path == "/api/overview/groups?dim=wrong" or path == "/__not_exist":
            expect_http = 400 if "dim=wrong" in path else 404
        elif "scope=wrong" in path or "signal_kind=__bad__" in path or "workflow_state=9" in path:
            expect_http = 400                                   # 非法入参必须被拦住
        else:
            expect_http = 200

        try:
            if method == "GET":
                resp = client.get(path, headers=headers)
            else:
                resp = client.post(path, json=body or {}, headers=headers)
            payload = resp.get_json() or {}
            data = payload.get("data")
            http_code, size = resp.status_code, len(resp.data)

            problems = []
            if resp.status_code != expect_http:
                problems.append(f"HTTP {resp.status_code} != 期望 {expect_http}")
            if payload.get("code") != expect_http:
                problems.append(f"body.code={payload.get('code')} != 期望 {expect_http}")
            if set(payload.keys()) != {"code", "data", "msg"}:
                problems.append(f"返回结构不统一: {list(payload.keys())}")
            if expect_http == 200 and isinstance(keys, list):
                missing = [k for k in keys if not _has(data, k)]
                if missing:
                    problems.append(f"缺字段 {missing}")
            status = "PASS" if not problems else "FAIL"
        except Exception as exc:                                       # noqa: BLE001
            status, problems = "FAIL", [f"异常 {type(exc).__name__}: {exc}"]
            payload, data, http_code, size = {}, None, 0, 0

        passed += status == "PASS"
        failed += status == "FAIL"
        print(f"[{status}] {method:<4} {path:<52} {http_code} {size / 1024:6.1f}KB"
              f"{'  ' + '; '.join(problems) if problems else ''}")
        if VERBOSE and isinstance(data, (dict, list)):
            preview = json.dumps(data, ensure_ascii=False, default=str)
            print(f"        {preview[:300]}")
    print("=" * 92)
    print(f"结果：{passed} 通过 / {failed} 失败")
    _cleanup_smoke_user(app, uid)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
