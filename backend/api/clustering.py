# -*- coding: utf-8 -*-
"""
聚类结果接口
  GET /api/clustering/result       K-Means 聚类结果（簇统计 + 逐学生归类 + 散点坐标）
  GET /api/clustering/elbow        手肘法 SSE 曲线 + 轮廓系数（论文里"如何确定 K"的依据）
  GET /api/clustering/members      某个簇的学生明细（点击簇查看成员）
  GET /api/clustering/table        逐学生归类扁平表（论文附表 / 前端表格）

参数：?k=4&refresh=1&start=&end=&days=&features=full|core
说明：
- 结果按 (窗口, k, 特征集) 做 TTL 缓存，refresh=1 强制重算。
- features=core 只用毕设总纲要求的 4 个特征，features=full（默认）用 11 个细分特征，
  两套结果可在论文里做特征消融对比。
"""

from __future__ import annotations

from flask import Blueprint, request

from analysis import clustering
from security import current_scope, has_perm, require_perm
from utils import fail, ok, parse_int, resolve_window

bp = Blueprint("clustering", __name__, url_prefix="/api/clustering")


def _feature_set() -> str:
    """特征集参数走分析层的白名单函数，非法值自动退回默认，不拼接进任何 SQL"""
    return clustering.normalize_feature_set(request.args.get("features"))


def _can_detail() -> bool:
    """是否可看个体身份（姓名/学院）。无 student:detail 者只能看匿名化聚类视图。"""
    return has_perm("student:detail")


@bp.get("/result")
@require_perm("clustering:read")
def result():
    k = parse_int("k", clustering_default_k(), 2, 12)
    start, end, days = resolve_window()
    refresh = request.args.get("refresh") in ("1", "true", "yes")
    fset = _feature_set()
    data = clustering.fit_kmeans(start, end, k, use_cache=not refresh, feature_set=fset,
                                 scope=current_scope())
    if data.get("error"):
        return fail(data["error"], 400, data)
    # 散点只需坐标+归属：万人规模下完整 points（含 features/percentiles）会把响应
    # 撑到几 MB。浅拷贝后换掉列表元素，缓存对象保持完整供 /table、/members、
    # 个体画像（feature_of_student）继续从进程内取全字段
    keep = ("student_id", "cluster", "x", "y", "name") if _can_detail() else ("student_id", "cluster", "x", "y")
    data = dict(data)
    data["points"] = [{kk: p[kk] for kk in keep} for p in data["points"]]
    if not _can_detail():
        data["clusters"] = [{**c, "top_students": [{kk: s.get(kk) for kk in
                                ("student_id", "avg_daily_amount", "avg_daily_study_minutes")}
                               for s in c.get("top_students", [])]} for c in data["clusters"]]
    data["days"] = days
    return ok(data)


@bp.get("/elbow")
@require_perm("clustering:read")
def elbow():
    """手肘法 + 轮廓系数双指标，前端画双 Y 轴折线；默认 K=2..8（聚合结果，不含个体身份）"""
    start, end, _ = resolve_window()
    k_max = parse_int("k_max", 8, 2, 12)
    k_min = parse_int("k_min", 2, 1, k_max)
    return ok({"window": [start, end],
               **clustering.elbow_curve(start, end, k_max, k_min, _feature_set(),
                                        scope=current_scope())})


@bp.get("/table")
@require_perm("clustering:read")
def table():
    """
    扁平归类表：一行一个学生 = 学号 + 各特征值 + 簇编号 + 簇标签。
    论文附录的"聚类结果一览表"和前端表格页共用这个接口（嵌套结构不利于直接转 CSV）。
    输出逐学生身份，属个体明细：仅持有 student:detail 且在其数据范围内的用户可用。
    """
    if not _can_detail():
        return fail("查看逐学生归类表需要个体明细权限", 403)
    k = parse_int("k", clustering_default_k(), 2, 12)
    limit = parse_int("limit", 300, 1, 2000)
    start, end, _ = resolve_window()
    fset = _feature_set()
    data = clustering.fit_kmeans(start, end, k, feature_set=fset, scope=current_scope())
    if data.get("error"):
        return fail(data["error"], 400, data)
    cols = data["feature_keys"]
    rows = []
    for p in data["points"]:
        row = {"student_id": p["student_id"], "name": p["name"], "college": p["college"],
               "cluster": p["cluster"], "label": p["label"]}
        row.update({fk: p["features"][fk] for fk in cols})
        rows.append(row)
    rows.sort(key=lambda r: (r["cluster"], -r["avg_daily_amount"]))
    return ok({"k": k, "feature_set": fset,
               "columns": ["student_id", "name", "college"] + cols + ["cluster", "label"],
               "column_labels": {fk: clustering.FEATURES[fk]["label"] for fk in cols},
               "total": len(rows), "items": rows[:limit],
               "window": [data["date_start"], data["date_end"]]})


@bp.get("/members")
@require_perm("clustering:read")
def members():
    """按簇取成员，按日均消费降序；输出逐学生身份，仅 student:detail 权限且范围内可用。"""
    if not _can_detail():
        return fail("查看簇成员明细需要个体明细权限", 403)
    cluster = parse_int("cluster", 0, 0, 11)
    k = parse_int("k", clustering_default_k(), 2, 12)
    limit = parse_int("limit", 50, 1, 500)
    start, end, _ = resolve_window()
    fset = _feature_set()
    data = clustering.fit_kmeans(start, end, k, feature_set=fset, scope=current_scope())
    if data.get("error"):
        return fail(data["error"], 400, data)
    info = {p["student_id"]: p for p in data["points"] if p["cluster"] == cluster}
    items = sorted(info.values(), key=lambda x: -x["features"]["avg_daily_amount"])[:limit]
    meta = next((c for c in data["clusters"] if c["cluster"] == cluster), None)
    return ok({"cluster": meta, "total": len(info), "feature_set": fset, "k": k,
               "page_total": data["n_students"], "items": items})


def _parse_windows(raw) -> list:
    """解析跨窗口参数：格式 's1~e1,s2~e2'，仅保留日期合法的前 3 组（供跨时间窗稳定性）。"""
    out = []
    for seg in str(raw or "").split(","):
        seg = seg.strip()
        if not seg or "~" not in seg:
            continue
        a, b = seg.split("~", 1)
        if parse_date_value(a) and parse_date_value(b):
            out.append([a.strip(), b.strip()])
        if len(out) >= 3:
            break
    return out


def parse_date_value(v):
    """宽松日期校验（YYYY-MM-DD 等），合法返回 True。不依赖 request 上下文。"""
    import datetime as dt
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            dt.datetime.strptime(str(v).strip(), fmt)
            return True
        except ValueError:
            continue
    return False


@bp.get("/experiment")
@require_perm("clustering:run")
def experiment():
    """
    同步 K-Means 算法实验（阶段 3）：预处理诊断 + 选 K + 多种子/重采样/跨窗稳定性
    + 特征集消融 + MiniBatch 效率对照。默认子采样 cap=3000 保证响应在可接受时间内返回。
    参数：?k=4&features=full|core&k_min=2&k_max=8&cap=3000&windows=2026-05-01~2026-05-20,...
    """
    from analysis import experiments
    start, end, _ = resolve_window()
    params = {
        "start": start, "end": end,
        "k": parse_int("k", clustering_default_k(), 2, 12),
        "feature_set": _feature_set(),
        "k_min": parse_int("k_min", 2, 2, 4),
        "k_max": parse_int("k_max", 8, 2, 12),
        "cap": parse_int("cap", 3000, 0, 20000),
        "windows": _parse_windows(request.args.get("windows")),
    }
    try:
        data = experiments.run_experiment(params, scope=current_scope())
    except ValueError as exc:
        return fail(str(exc), 400)
    return ok(data)


@bp.get("/iforest")
@require_perm("clustering:run")
def iforest():
    """
    IsolationForest 独立异常检测实验（阶段 3 第 5 条）：只返回【聚合】分数分布与离群计数，
    绝不导出个人名单、不映射为学生风险。参数：?features=full|core
    """
    from analysis import outlier_exp
    start, end, _ = resolve_window()
    try:
        data = outlier_exp.run_iforest({"start": start, "end": end, "feature_set": _feature_set()},
                                        scope=current_scope())
    except ValueError as exc:
        return fail(str(exc), 400)
    return ok(data)


def clustering_default_k() -> int:
    """默认 K 从配置读，便于不改代码调整"""
    from flask import current_app

    return int(current_app.config.get("CLUSTERING_K", 4))
