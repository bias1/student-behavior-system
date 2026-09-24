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
from utils import fail, ok, parse_int, resolve_window

bp = Blueprint("clustering", __name__, url_prefix="/api/clustering")


def _feature_set() -> str:
    """特征集参数走分析层的白名单函数，非法值自动退回默认，不拼接进任何 SQL"""
    return clustering.normalize_feature_set(request.args.get("features"))


@bp.get("/result")
def result():
    k = parse_int("k", clustering_default_k(), 2, 12)
    start, end, days = resolve_window()
    refresh = request.args.get("refresh") in ("1", "true", "yes")
    fset = _feature_set()
    data = clustering.fit_kmeans(start, end, k, use_cache=not refresh, feature_set=fset)
    if data.get("error"):
        return fail(data["error"], 400, data)
    data["days"] = days
    return ok(data)


@bp.get("/elbow")
def elbow():
    """手肘法 + 轮廓系数双指标，前端画双 Y 轴折线；默认 K=2..8"""
    start, end, _ = resolve_window()
    k_max = parse_int("k_max", 8, 2, 12)
    k_min = parse_int("k_min", 2, 1, k_max)
    return ok({"window": [start, end],
               **clustering.elbow_curve(start, end, k_max, k_min, _feature_set())})


@bp.get("/table")
def table():
    """
    扁平归类表：一行一个学生 = 学号 + 各特征值 + 簇编号 + 簇标签。
    论文附录的"聚类结果一览表"和前端表格页共用这个接口（嵌套结构不利于直接转 CSV）。
    """
    k = parse_int("k", clustering_default_k(), 2, 12)
    limit = parse_int("limit", 300, 1, 2000)
    start, end, _ = resolve_window()
    fset = _feature_set()
    data = clustering.fit_kmeans(start, end, k, feature_set=fset)
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
def members():
    """按簇取成员，按日均消费降序，便于在簇内快速找到极端样本"""
    cluster = parse_int("cluster", 0, 0, 11)
    k = parse_int("k", clustering_default_k(), 2, 12)
    limit = parse_int("limit", 50, 1, 500)
    start, end, _ = resolve_window()
    fset = _feature_set()
    data = clustering.fit_kmeans(start, end, k, feature_set=fset)
    if data.get("error"):
        return fail(data["error"], 400, data)
    info = {p["student_id"]: p for p in data["points"] if p["cluster"] == cluster}
    items = sorted(info.values(), key=lambda x: -x["features"]["avg_daily_amount"])[:limit]
    meta = next((c for c in data["clusters"] if c["cluster"] == cluster), None)
    return ok({"cluster": meta, "total": len(info), "feature_set": fset, "k": k,
               "page_total": data["n_students"], "items": items})


def clustering_default_k() -> int:
    """默认 K 从配置读，便于不改代码调整"""
    from flask import current_app

    return int(current_app.config.get("CLUSTERING_K", 4))
