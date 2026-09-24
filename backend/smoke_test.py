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

from app import create_app

VERBOSE = "-v" in sys.argv

# (方法, 路径, JSON体, 断言：data 里必须存在的字段)
CASES = [
    ("GET", "/api/health", None, ["status", "tables"]),
    ("GET", "/", None, ["endpoints"]),
    ("GET", "/api/overview", None,
     ["student_count", "total_amount", "avg_daily_study_minutes", "consume_peak_hour"]),
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
    ("GET", "/api/warning/stats", None, ["total", "by_type", "by_rule", "trend"]),
    ("GET", "/api/warning/rules", None, None),                       # 返回 list，无 dict 字段
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


def main() -> int:
    app = create_app()
    client = app.test_client()
    passed = failed = 0
    sid = None

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
        elif "scope=wrong" in path:
            expect_http = 400                                   # 非法 scope 必须被拦住
        else:
            expect_http = 200

        try:
            if method == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path, json=body or {})
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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
