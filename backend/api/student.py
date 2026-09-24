# -*- coding: utf-8 -*-
"""
个体画像接口
  GET /api/student/list                     学生检索（学号/姓名/学院，分页）
  GET /api/student/<id>/profile             个体画像聚合数据（一页一接口，减少请求数）
  GET /api/student/<id>/consumption         消费流水明细分页（表格用）
  GET /api/student/<id>/library             进馆记录明细分页（表格用）

profile 返回结构（前端画像页各图一一对应）：
  info     基本信息        kpi      核心指标 + 群体对比
  radar    五维雷达（群体内百分位）  cluster  所属画像簇
  daily    按天趋势        meal_dist/hour_dist  餐段与作息分布
  warnings 该生历史预警
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
from flask import Blueprint, request
from sqlalchemy import text

from analysis import clustering
from models import Student, Warning, db
from utils import fail, ok, parse_int, resolve_window

bp = Blueprint("student", __name__, url_prefix="/api/student")

# 学生窗口内按天聚合：一次查询同时供 KPI、趋势、缺餐率使用
# night 的区间固定为 23:00-05:00，与预警规则 NIGHT_CONSUME、聚类特征 night_ratio 同一口径
SQL_DAILY_CONS = """
    SELECT DATE(consumed_at) AS d, SUM(amount) AS amt, COUNT(*) AS n,
           MAX(meal_period = '早餐') AS b, MAX(meal_period = '午餐') AS l,
           MAX(meal_period = '晚餐') AS dn,
           SUM(CASE WHEN HOUR(consumed_at) >= 23 OR HOUR(consumed_at) < 5 THEN 1 ELSE 0 END) AS night,
           SUM(merchant_type = 2) AS supermarket
    FROM consumption
    WHERE is_valid = 1 AND student_id = :sid
      AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
    GROUP BY d ORDER BY d
"""

SQL_HOURS = """
    SELECT HOUR(consumed_at) h, COUNT(*) n, ROUND(SUM(amount),2) amt
    FROM consumption WHERE is_valid = 1 AND student_id = :sid
      AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
    GROUP BY h ORDER BY h
"""

SQL_MERCHANTS = """
    SELECT merchant_name, merchant_type, COUNT(*) n, ROUND(SUM(amount),2) amt
    FROM consumption WHERE is_valid = 1 AND student_id = :sid
      AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
    GROUP BY merchant_name, merchant_type ORDER BY n DESC LIMIT 8
"""

SQL_LIB_DAILY = """
    SELECT DATE(gate_in_time) d, COUNT(*) visits, SUM(stay_minutes) mins,
           MAX(HOUR(gate_in_time) >= 18) evening
    FROM library_record WHERE is_valid = 1 AND student_id = :sid
      AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
    GROUP BY d ORDER BY d
"""

SQL_LIB_HOURS = """
    SELECT HOUR(gate_in_time) h, COUNT(*) n FROM library_record
    WHERE is_valid = 1 AND student_id = :sid
      AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
    GROUP BY h ORDER BY h
"""

# 雷达图维度：(显示名, 特征 key, 是否反向)。两套特征集各自的维度，保证"核心 4 特征"也能完整成图
# 反向用于"越小越好"的指标（消费波动、时间离散度），取 100-百分位后才能统一朝外读
RADAR_DIMS: Dict[str, tuple] = {
    "full": (("消费水平", "avg_daily_amount", False), ("学习强度", "library_days_ratio", False),
             ("三餐规律", "meal_reg", False), ("作息稳定", "amount_cv", True),
             ("晚间自习", "evening_study_ratio", False)),
    "core": (("消费水平", "avg_daily_amount", False), ("消费频次", "avg_daily_records", False),
             ("学习强度", "avg_daily_study_minutes", False), ("时间规律", "meal_time_std", True)),
}


@bp.get("/list")
def student_list():
    """学生检索：支持学号精确/姓名前缀/学院筛选，个体画像页的搜索框数据源"""
    keyword = (request.args.get("keyword") or "").strip()
    college = request.args.get("college")
    page, size = parse_int("page", 1, 1, 10000), parse_int("size", 20, 1, 200)

    q = Student.query
    if keyword:
        # 前缀匹配能走 idx_student_name；% 需转义，避免用户输入把 LIKE 变成全表扫描
        like = keyword.replace("%", r"\%").replace("_", r"\_")
        q = q.filter(db.or_(Student.student_id.like(f"{like}%"), Student.name.like(f"{like}%")))
    if college:
        q = q.filter(Student.college == college)
    total = q.count()
    rows = q.order_by(Student.student_id).offset((page - 1) * size).limit(size).all()
    return ok({"total": total, "page": page, "size": size,
               "items": [s.to_dict() for s in rows]})


@bp.get("/<sid>/profile")
def profile(sid: str):
    """个体画像主接口"""
    stu = db.session.get(Student, sid)
    if stu is None:
        return fail(f"学号 {sid} 不存在", 404)

    start, end, days = resolve_window()
    p = {"sid": sid, "start": start, "end": end}

    daily = pd.read_sql(text(SQL_DAILY_CONS), con=db.engine, params=p)
    hours = pd.read_sql(text(SQL_HOURS), con=db.engine, params=p)
    merch = pd.read_sql(text(SQL_MERCHANTS), con=db.engine, params=p)
    lib_daily = pd.read_sql(text(SQL_LIB_DAILY), con=db.engine, params=p)
    lib_hours = pd.read_sql(text(SQL_LIB_HOURS), con=db.engine, params=p)

    # ---------- 补齐日期轴：无消费/无进馆的日期也要出现，趋势图才不会"看起来只有几天" ----------
    idx = pd.date_range(start=start, end=end, freq="D")
    if len(daily):
        daily = daily.set_index(pd.DatetimeIndex(pd.to_datetime(daily["d"]))).reindex(idx, fill_value=0)
    else:
        daily = pd.DataFrame({"amt": 0.0, "n": 0, "b": 0, "l": 0, "dn": 0, "night": 0,
                              "supermarket": 0}, index=idx)
    if len(lib_daily):
        lib_daily = lib_daily.set_index(pd.DatetimeIndex(pd.to_datetime(lib_daily["d"]))).reindex(idx, fill_value=0)
    else:
        lib_daily = pd.DataFrame({"visits": 0, "mins": 0, "evening": 0}, index=idx)

    active_days = int((daily["n"] > 0).sum())
    meals = daily[["b", "l", "dn"]].astype(bool).sum(axis=1)          # 每天覆盖了几个正餐段
    total_amount = round(float(daily["amt"].sum()), 2)
    lib_visits = int(lib_daily["visits"].sum())
    lib_minutes = float(lib_daily["mins"].fillna(0).sum())

    # ---------- 画像簇与群体分位（复用聚类的缓存结果，不重复训练模型） ----------
    # ?features=core|full 与聚类接口保持一致，否则大屏选 core、画像返 full 会造成簇标签对不上
    fset = clustering.normalize_feature_set(request.args.get("features"))
    clu = clustering.feature_of_student(sid, start, end, feature_set=fset)
    summary = clustering.group_summary(start, end, fset)

    kpi = {
        # 消费维度
        "total_amount": total_amount,
        "records": int(daily["n"].sum()),
        "active_days": active_days,
        "avg_daily_amount": round(total_amount / days, 2),            # 分母用窗口天数，缺失天也计入
        "avg_daily_records": round(int(daily["n"].sum()) / days, 2),   # 日均消费频次（与聚类特征同口径）
        "avg_daily_study_minutes": round(lib_minutes / days, 1),      # 日均图书馆时长（与聚类特征同口径）
        "avg_daily_amount_active": round(total_amount / active_days, 2) if active_days else 0.0,
        "avg_per_record": round(float(daily["amt"].sum() / max(1, daily["n"].sum())), 2),
        "amount_std": round(float(daily["amt"].std() or 0), 2),
        "night_times": int(daily["night"].sum()),
        "supermarket_times": int(daily["supermarket"].sum()),
        # 三餐规律：覆盖 3 个正餐段的天数占比；缺餐率是预警模块的核心输入
        "all3_meal_days": int((meals == 3).sum()),
        "meal_regular_rate": round(float((meals == 3).sum() / days * 100), 1),
        "missing_meal_rate": round(float((1 - meals.mean() / 3) * 100), 1) if days else 0.0,
        # 学习维度
        "library_visits": lib_visits,
        "library_days": int((lib_daily["visits"] > 0).sum()),
        "library_days_ratio": round(float((lib_daily["visits"] > 0).sum() / days * 100), 1),
        "total_study_hours": round(lib_minutes / 60, 1),
        "avg_study_minutes_per_day": round(lib_minutes / days, 1),
        "avg_stay_minutes": round(lib_minutes / lib_visits, 1) if lib_visits else 0.0,
        "evening_study_visits": int(lib_daily["evening"].sum()),
    }

    # ---------- 雷达图：把维度换成"在群体中的百分位"，同一尺度才可画多边形 ----------
    pct = (clu or {}).get("percentiles", {})
    dims = RADAR_DIMS[fset]
    radar = {
        "indicators": [{"name": n, "max": 100} for n, _, _ in dims],
        "values": [(round(100 - pct.get(k, 50), 1) if rev else pct.get(k, 50)) if pct else 50
                   for _, k, rev in dims],
        # 百分位背后的特征名一并发给前端，鼠标悬停时能显示"学习强度 78 ← 日均在馆 128 分钟"
        "keys": [k for _, k, _ in dims],
        # 同时给原始值，前端 tooltip 显示"日均消费 18.3 元（超过全校 72% 的学生）"
        "raw": (clu or {}).get("features", {}),
        "group_mean": summary["mean"],
        "group_median": summary["median"],
    }

    warnings = (Warning.query.filter_by(student_id=sid)
                .order_by(Warning.warning_date.desc()).limit(20).all())

    return ok({
        "info": stu.to_dict(),
        "window": [start, end],
        "days": days,
        "kpi": kpi,
        "radar": radar,
        "cluster": None if not clu else {
            "cluster": clu["cluster"], "label": clu["label"], "k": clu["k"],
            "feature_set": fset, "features": clu["features"],
            # desc 由该簇 z 分数自动生成，definition 是画像类型的通用解释（两者同源不同用）
            "desc": clu.get("desc"), "definition": clu.get("definition"),
            "cluster_mean": clu.get("cluster_features"),
        },
        "daily": {
            "dates": [d.strftime("%m-%d") for d in idx],
            "amount": [round(float(v), 2) for v in daily["amt"]],
            "records": [int(v) for v in daily["n"]],
            "meals": [int(v) for v in meals],
            "library_minutes": [round(float(v or 0) / 60, 2) for v in lib_daily["mins"]],
            "library_visits": [int(v) for v in lib_daily["visits"]],
        },
        "hour_dist": [{"hour": int(r["h"]), "n": int(r["n"]), "amount": round(float(r["amt"] or 0), 2)}
                      for _, r in hours.iterrows()],
        "library_hour_dist": [{"hour": int(r["h"]), "n": int(r["n"])} for _, r in lib_hours.iterrows()],
        "top_merchants": [{"merchant_name": r["merchant_name"], "merchant_type": int(r["merchant_type"]),
                           "n": int(r["n"]), "amount": round(float(r["amt"] or 0), 2)}
                          for _, r in merch.iterrows()],
        "warnings": [w.to_dict() for w in warnings],
    })


@bp.get("/<sid>/consumption")
def consumption_detail(sid: str):
    """消费流水明细（分页表格）；page/size 上限做保护，避免一次拉空表"""
    if db.session.get(Student, sid) is None:
        return fail(f"学号 {sid} 不存在", 404)
    start, end, _ = resolve_window()
    page, size = parse_int("page", 1, 1, 10000), parse_int("size", 20, 1, 200)
    df = pd.read_sql(text("""
        SELECT id, merchant_type, merchant_name, amount, balance, consumed_at, meal_period, terminal_id
        FROM consumption
        WHERE is_valid = 1 AND student_id = :sid
          AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        ORDER BY consumed_at DESC LIMIT :size OFFSET :off
        """), con=db.engine, params={"sid": sid, "start": start, "end": end,
                                     "size": size, "off": (page - 1) * size})
    total = pd.read_sql(text("""
        SELECT COUNT(*) n, ROUND(SUM(amount),2) amt FROM consumption
        WHERE is_valid = 1 AND student_id = :sid
          AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        """), con=db.engine, params={"sid": sid, "start": start, "end": end}).iloc[0]
    rows = df.replace({np.nan: None}).to_dict(orient="records")
    for r in rows:
        if r.get("amount") is not None:
            r["amount"] = round(float(r["amount"]), 2)
        if r.get("balance") is not None:
            r["balance"] = round(float(r["balance"]), 2)
    return ok({"total": int(total["n"]), "page": page, "size": size,
               "window": [start, end], "items": rows})


@bp.get("/<sid>/library")
def library_detail(sid: str):
    """进馆记录明细（分页表格），含自动计算出的停留时长"""
    if db.session.get(Student, sid) is None:
        return fail(f"学号 {sid} 不存在", 404)
    start, end, _ = resolve_window()
    page, size = parse_int("page", 1, 1, 10000), parse_int("size", 20, 1, 200)
    df = pd.read_sql(text("""
        SELECT id, venue, floor_no, area_name, seat_no, gate_in_time, gate_out_time,
               stay_minutes, in_meal_flag
        FROM library_record
        WHERE is_valid = 1 AND student_id = :sid
          AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        ORDER BY gate_in_time DESC LIMIT :size OFFSET :off
        """), con=db.engine, params={"sid": sid, "start": start, "end": end,
                                     "size": size, "off": (page - 1) * size})
    total = pd.read_sql(text("""
        SELECT COUNT(*) n FROM library_record
        WHERE is_valid = 1 AND student_id = :sid
          AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        """), con=db.engine, params={"sid": sid, "start": start, "end": end}).iloc[0]["n"]
    return ok({"total": int(total), "page": page, "size": size, "window": [start, end],
               "items": df.replace({np.nan: None}).to_dict(orient="records")})
