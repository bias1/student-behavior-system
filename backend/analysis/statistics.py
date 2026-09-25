# -*- coding: utf-8 -*-
"""
分析层：基础统计（pandas 实现）

设计约定：
1. 所有统计一律带 is_valid=1 条件 —— 脏数据只能在清洗环节处理，不能污染分析结果。
2. SQL 只做"取数 + 粗聚合"，补齐日期轴、透视矩阵、占比计算交给 pandas，
   这样分析逻辑可单测、可迁移（论文里也好解释）。
3. 时间参数统一用命名绑定参数，杜绝 SQL 注入。
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sqlalchemy import text

from models import db
from utils import data_range

WEEKDAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
HOURS = list(range(24))


def _read(sql: str, params: Dict[str, Any] | None = None) -> pd.DataFrame:
    """统一读库入口（SQLAlchemy 连接复用 Flask-SQLAlchemy 引擎）"""
    return pd.read_sql(text(sql), con=db.engine, params=params or {})


# =============================================================================
# 1. 总览指标
# =============================================================================

def overview() -> Dict[str, Any]:
    """大屏顶部核心指标卡：学生数、消费总额、日均图书馆时长等"""
    start, end = data_range()
    sql = """
        SELECT COUNT(DISTINCT student_id)                              AS students,
               COUNT(*)                                                 AS records,
               ROUND(SUM(amount), 2)                                    AS total_amount,
               ROUND(AVG(amount), 2)                                    AS avg_amount,
               ROUND(SUM(amount) / COUNT(DISTINCT student_id) /
                     (DATEDIFF(MAX(DATE(consumed_at)), MIN(DATE(consumed_at))) + 1), 2)
                                                                        AS avg_daily_amount,
               MIN(DATE(consumed_at))                                   AS c_start,
               MAX(DATE(consumed_at))                                   AS c_end
        FROM consumption WHERE is_valid = 1
    """
    c = _read(sql).iloc[0]

    sql_lib = """
        SELECT COUNT(*)                                    AS visits,
               COUNT(DISTINCT student_id)                  AS students,
               ROUND(AVG(stay_minutes), 1)                 AS avg_stay,
               ROUND(SUM(stay_minutes) / (DATEDIFF(MAX(DATE(gate_in_time)),
                                                   MIN(DATE(gate_in_time))) + 1) / 60, 2)
                                                           AS daily_hours_total,
               ROUND(SUM(stay_minutes) / COUNT(DISTINCT student_id) /
                     (DATEDIFF(MAX(DATE(gate_in_time)), MIN(DATE(gate_in_time))) + 1) / 60, 2)
                                                           AS avg_daily_hours
        FROM library_record WHERE is_valid = 1 AND stay_minutes IS NOT NULL
    """
    l = _read(sql_lib).iloc[0]

    # 高峰时段：消费笔数最多的小时 / 进馆人数最多的小时
    peak_c = _read("SELECT HOUR(consumed_at) h, COUNT(*) n FROM consumption WHERE is_valid=1 "
                   "GROUP BY h ORDER BY n DESC LIMIT 1")
    peak_l = _read("SELECT HOUR(gate_in_time) h, COUNT(*) n FROM library_record WHERE is_valid=1 "
                   "GROUP BY h ORDER BY n DESC LIMIT 1")

    warn = _read("SELECT COUNT(*) n, SUM(status=0) pending FROM warning")
    stu = _read("SELECT COUNT(*) n FROM student").iloc[0]

    return {
        "student_count": int(stu["n"]),
        "consumption_records": int(c["records"]),
        "library_records": int(l["visits"]),
        "total_amount": float(c["total_amount"] or 0),
        "avg_amount": float(c["avg_amount"] or 0),
        # 人均日消费：判断"消费骤降"类预警的基准线
        "avg_daily_amount": float(c["avg_daily_amount"] or 0),
        "avg_daily_study_minutes": round(float(l["avg_daily_hours"] or 0) * 60, 1),
        "avg_daily_study_hours": float(l["avg_daily_hours"] or 0),
        "total_study_hours": round(float(l["daily_hours_total"] or 0), 1),
        "consume_peak_hour": int(peak_c.iloc[0]["h"]) if len(peak_c) else None,
        "library_peak_hour": int(peak_l.iloc[0]["h"]) if len(peak_l) else None,
        "warning_count": int(warn.iloc[0]["n"] or 0),
        "warning_pending": int(warn.iloc[0]["pending"] or 0),
        "date_start": str(c["c_start"]),
        "date_end": str(c["c_end"]),
    }


# =============================================================================
# 2. 消费相关统计
# =============================================================================

def consumption_trend(start: str, end: str) -> Dict[str, Any]:
    """
    按天消费趋势：总额、笔数、人均笔数、在馆时长（叠加对比用）。
    缺失日期用 reindex 补 0，否则前端折线会在周末断线，看起来像数据丢失。
    """
    df = _read(
        """
        SELECT DATE(consumed_at) d, ROUND(SUM(amount),2) amount, COUNT(*) records,
               COUNT(DISTINCT student_id) students
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY d ORDER BY d
        """,
        {"start": start, "end": end},
    )
    lib = _read(
        """
        SELECT DATE(gate_in_time) d, COUNT(*) visits, ROUND(SUM(stay_minutes),0) minutes
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY d
        """,
        {"start": start, "end": end},
    )
    if len(df) == 0:
        return {"dates": [], "series": {}}

    idx = pd.date_range(start=df["d"].min(), end=df["d"].max(), freq="D")
    # 索引用 DatetimeIndex 与 idx 类型对齐（用 datetime.date 会因类型不一致而 reindex 全部落空）
    df = df.set_index(pd.DatetimeIndex(pd.to_datetime(df["d"]))).reindex(idx, fill_value=0)
    if len(lib):
        lib = lib.set_index(pd.DatetimeIndex(pd.to_datetime(lib["d"]))).reindex(idx, fill_value=0)

    dates = [d.strftime("%Y-%m-%d") for d in idx]
    return {
        "dates": dates,
        "weekday": [WEEKDAYS_CN[d.weekday()] for d in idx],
        "is_weekend": [1 if d.weekday() >= 5 else 0 for d in idx],
        "series": {
            "amount": [round(float(v), 2) for v in df["amount"]],
            "records": [int(v) for v in df["records"]],
            "students": [int(v) for v in df["students"]],
            # 人均笔数：逐日用"当日笔数 / 当日消费人数"。旧实现除的是窗口内最大人数，
            # 周末只有 20 人消费时会被 100 人的峰值分母摊薄，工作日/周末对比彻底失真
            "avg_records_per_student": [round(float(r) / max(1, int(s)), 2)
                                        for r, s in zip(df["records"], df["students"])],
            "library_visits": [int(v) for v in (lib["visits"] if len(lib) else [0] * len(idx))],
            "library_minutes": [round(float(v or 0) / 60, 2) for v in
                                (lib["minutes"] if len(lib) else [0] * len(idx))],
        },
        "summary": {
            "weekday_avg_amount": round(float(df[[d.weekday() < 5 for d in idx]]["amount"].mean() or 0), 2),
            "weekend_avg_amount": round(float(df[[d.weekday() >= 5 for d in idx]]["amount"].mean() or 0), 2),
        },
    }


def consumption_heatmap(start: str, end: str) -> Dict[str, Any]:
    """
    消费时段热力图：星期(7) × 小时(24) 的笔数与金额矩阵。
    MySQL WEEKDAY() 返回 0=周一，与前端 x 轴顺序一致；网格补 0 后再透视，
    否则 ECharts 会把缺值当 0 但颜色映射的 max 会算错。
    """
    df = _read(
        """
        SELECT WEEKDAY(consumed_at) wd, HOUR(consumed_at) hh,
               COUNT(*) records, ROUND(SUM(amount),2) amount
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY wd, hh
        """,
        {"start": start, "end": end},
    )
    full = pd.MultiIndex.from_product([range(7), HOURS], names=["wd", "hh"]).to_frame(index=False)
    df = full.merge(df, on=["wd", "hh"], how="left").fillna({"records": 0, "amount": 0})

    def cells(col: str) -> List[List[Any]]:
        return [[int(r["hh"]), int(r["wd"]), int(r[col]) if col == "records" else round(float(r[col]), 2)]
                for _, r in df.iterrows()]

    by_hour = df.groupby("hh", as_index=False)[["records", "amount"]].sum()
    return {
        "hours": HOURS,
        "weekdays": WEEKDAYS_CN,
        "data": cells("records"),
        "amount_data": cells("amount"),
        "max_records": int(df["records"].max() or 0),
        "max_amount": round(float(df["amount"].max() or 0), 2),
        # 小时边际分布：给"消费时段柱状图"复用，省一次请求
        "hour_dist": [{"hour": int(r["hh"]), "records": int(r["records"]),
                       "amount": round(float(r["amount"]), 2)} for _, r in by_hour.iterrows()],
    }


def consumption_category(start: str, end: str) -> Dict[str, Any]:
    """消费类别占比：按商户类型 + 按餐段（meal_period 是数据库生成列）"""
    by_type = _read(
        """
        SELECT merchant_type, COUNT(*) records, ROUND(SUM(amount),2) amount,
               ROUND(AVG(amount),2) avg_amount
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY merchant_type ORDER BY amount DESC
        """,
        {"start": start, "end": end},
    )
    by_meal = _read(
        """
        SELECT meal_period, COUNT(*) records, ROUND(SUM(amount),2) amount
        FROM consumption
        WHERE is_valid = 1 AND merchant_type = 1
          AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY meal_period ORDER BY records DESC
        """,
        {"start": start, "end": end},
    )
    by_top_merchant = _read(
        """
        SELECT merchant_name, COUNT(*) records, ROUND(SUM(amount),2) amount
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY merchant_name ORDER BY records DESC LIMIT 10
        """,
        {"start": start, "end": end},
    )

    def with_pct(df: pd.DataFrame, key: str) -> List[Dict[str, Any]]:
        total = float(df["amount"].sum() or 0)
        recs = float(df["records"].sum() or 0)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                key: r[key],
                "records": int(r["records"]),
                "amount": round(float(r["amount"]), 2),
                "amount_pct": round(float(r["amount"]) / total * 100, 2) if total else 0.0,
                "records_pct": round(float(r["records"]) / recs * 100, 2) if recs else 0.0,
                **({"avg_amount": round(float(r["avg_amount"]), 2)} if "avg_amount" in df.columns else {}),
            })
        return rows

    return {
        "by_merchant_type": with_pct(by_type.assign(
            merchant_type=by_type["merchant_type"].map({1: "食堂", 2: "超市", 3: "浴室", 4: "机房", 5: "其他"})
            .fillna("其他")), "merchant_type"),
        "by_meal_period": with_pct(by_meal, "meal_period"),
        "top_merchants": with_pct(by_top_merchant, "merchant_name"),
    }


# =============================================================================
# 3. 图书馆相关统计
# =============================================================================

def library_trend(start: str, end: str) -> Dict[str, Any]:
    """图书馆人流趋势：按天的入馆人次、独立人数、日均在馆时长、高峰小时"""
    df = _read(
        """
        SELECT DATE(gate_in_time) d, COUNT(*) visits, COUNT(DISTINCT student_id) students,
               ROUND(AVG(stay_minutes),1) avg_stay, ROUND(SUM(stay_minutes)/60,1) total_hours
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY d ORDER BY d
        """,
        {"start": start, "end": end},
    )
    if len(df) == 0:
        return {"dates": [], "series": {}}
    idx = pd.date_range(start=df["d"].min(), end=df["d"].max(), freq="D")
    df = df.set_index(pd.DatetimeIndex(pd.to_datetime(df["d"]))).reindex(idx, fill_value=0)

    hourly = _read(
        """
        SELECT WEEKDAY(gate_in_time) wd, HOUR(gate_in_time) hh, COUNT(*) n
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY wd, hh
        """,
        {"start": start, "end": end},
    )
    full = pd.MultiIndex.from_product([range(7), HOURS], names=["wd", "hh"]).to_frame(index=False)
    grid = full.merge(hourly, on=["wd", "hh"], how="left").fillna({"n": 0})

    area = _read(
        """
        SELECT area_name, COUNT(*) n FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY area_name ORDER BY n DESC LIMIT 8
        """,
        {"start": start, "end": end},
    )
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "weekday": [WEEKDAYS_CN[d.weekday()] for d in idx],
        "series": {
            "visits": [int(v) for v in df["visits"]],
            "students": [int(v) for v in df["students"]],
            "avg_stay_minutes": [round(float(v or 0), 1) for v in df["avg_stay"]],
            "total_hours": [round(float(v or 0), 1) for v in df["total_hours"]],
        },
        "heatmap": {
            "hours": HOURS,
            "weekdays": WEEKDAYS_CN,
            "data": [[int(r["hh"]), int(r["wd"]), int(r["n"])] for _, r in grid.iterrows()],
            "max": int(grid["n"].max() or 0),
        },
        "hour_dist": [{"hour": h, "n": int(grid[grid.hh == h]["n"].sum())} for h in HOURS],
        "area_dist": [{"area_name": r["area_name"], "n": int(r["n"])} for _, r in area.iterrows()],
    }


# =============================================================================
# 4. 群体结构统计（大屏"学院对比 / 年级对比"用）
# =============================================================================

def group_distribution(start: str, end: str, dim: str = "college") -> List[Dict[str, Any]]:
    """
    按学院/年级/性别看"人均消费 + 人均学习时长"，同一口径便于横向比较。
    dim 走白名单校验，绝不能把用户输入直接拼进 SQL。
    """
    col = {"college": "college", "grade": "grade_year", "gender": "gender", "major": "major"}.get(dim)
    if col is None:
        return []
    df = _read(
        f"""
        SELECT s.{col} AS dim,
               COUNT(DISTINCT s.student_id)                              AS students,
               ROUND(SUM(c.amount) / COUNT(DISTINCT s.student_id), 2)     AS avg_amount,
               COUNT(c.id)                                               AS records
        FROM student s LEFT JOIN consumption c
               ON c.student_id = s.student_id AND c.is_valid = 1
              AND c.consumed_at >= :start AND c.consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY dim ORDER BY avg_amount DESC
        """,
        {"start": start, "end": end},
    )
    lib = _read(
        f"""
        SELECT s.{col} AS dim, ROUND(SUM(l.stay_minutes) / COUNT(DISTINCT s.student_id) / 60, 2) AS hours,
               COUNT(DISTINCT l.student_id) AS visitors
        FROM student s LEFT JOIN library_record l
               ON l.student_id = s.student_id AND l.is_valid = 1
              AND l.gate_in_time >= :start AND l.gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY dim
        """,
        {"start": start, "end": end},
    )
    merged = df.merge(lib, on="dim", how="left", suffixes=("", "_lib")).fillna({"hours": 0, "visitors": 0})

    def _label(v: Any) -> str:
        """性别是编码列，直接 str() 会让大屏图例出现 "1"/"2"，须按数据字典翻译回文本"""
        if col == "gender":
            return {1: "男", 2: "女"}.get(int(v), "未知")
        return str(v)

    return [{
        "name": _label(r["dim"]),
        "students": int(r["students"]),
        "avg_amount": round(float(r["avg_amount"] or 0), 2),
        "records": int(r["records"] or 0),
        "avg_study_hours": round(float(r["hours"] or 0), 2),
        # 进馆人数占比：识别"学习氛围"差异，而不是只看总量
        "library_rate": round(float(r["visitors"]) / max(1, int(r["students"])) * 100, 1),
    } for _, r in merged.iterrows()]


def consumption_rank(start: str, end: str, limit: int = 10, order: str = "desc") -> List[Dict[str, Any]]:
    """消费金额排行（order=asc 时用于找"疑似经济困难/节食"学生）"""
    direction = "ASC" if str(order).lower() == "asc" else "DESC"   # 白名单，不拼用户输入
    df = _read(
        f"""
        SELECT c.student_id, s.name, s.college, s.class_name,
               ROUND(SUM(c.amount),2) total, COUNT(*) records, ROUND(AVG(c.amount),2) avg_amount
        FROM consumption c JOIN student s ON s.student_id = c.student_id
        WHERE c.is_valid = 1 AND c.consumed_at >= :start AND c.consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY c.student_id ORDER BY total {direction} LIMIT :limit
        """,
        {"start": start, "end": end, "limit": int(limit)},
    )
    return df.replace({np.nan: None}).to_dict(orient="records")


# =============================================================================
# 5. 汇总接口（概览页 KPI 卡、环比 / 小泡图）
# =============================================================================

import datetime as _dt  # noqa: E402  局部导入，避免与上面主体冲突


def summary_metrics(start: str, end: str, days: int) -> Dict[str, Any]:
    """
    概览页汇总指标。

    返回字段:
      window / prev_window   当前窗口与上一环比窗口（字符串 [start, end]）
      student_count          全库学生数
      active_rate            窗口内有过消费 OR 进馆的学生占比 (%)
      total_amount           窗口内消费总额
      avg_daily_study_minutes  日均图书馆时长（人均，分）
      warning_count          累计预警总数
      warning_pending        未处理预警数
      amount_delta           消费总额环比 (%)，前窗口为 0 时返回 None
      study_delta            日均在馆时长环比 (%)
      warning_delta          新增预警环比 (%)
      active_delta           活跃率环比 (百分点)
      spark_amount           窗口内每日消费额（小泡图）
      spark_library          窗口内每日在馆分钟
      spark_warning          窗口内每日新增预警数
    """
    # ---------- 上一窗口 ----------
    s_dt = _dt.date.fromisoformat(start)
    e_dt = _dt.date.fromisoformat(end)
    prev_s = (s_dt - _dt.timedelta(days=days)).isoformat()
    prev_e = (s_dt - _dt.timedelta(days=1)).isoformat()

    # ---------- 当前窗口数据 ----------
    stu_total = int(_read("SELECT COUNT(*) n FROM student").iloc[0]["n"] or 0)

    cur = _read(
        """
        SELECT SUM(amount) total_amount,
               COUNT(DISTINCT student_id) active_students
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        """,
        {"start": start, "end": end},
    ).iloc[0]
    cur_lib = _read(
        """
        SELECT ROUND(SUM(stay_minutes) / NULLIF(COUNT(DISTINCT student_id), 0) / :days, 1) avg_daily_min,
               COUNT(DISTINCT student_id) lib_students
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        """,
        {"start": start, "end": end, "days": days},
    ).iloc[0]
    warn_row = _read(
        "SELECT COUNT(*) n, SUM(status=0) pending FROM warning"
    ).iloc[0]
    new_warn_cur = int(_read(
        "SELECT COUNT(*) n FROM warning WHERE warning_date >= :start AND warning_date <= :end",
        {"start": start, "end": end},
    ).iloc[0]["n"] or 0)

    # 当前窗口内有过消费 OR 进馆的学生数（去重）
    active_combined = int(_read(
        """
        SELECT COUNT(DISTINCT student_id) n FROM (
            SELECT student_id FROM consumption
            WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
            UNION
            SELECT student_id FROM library_record
            WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        ) t
        """,
        {"start": start, "end": end},
    ).iloc[0]["n"] or 0)

    # ---------- 上一窗口数据（环比） ----------
    prev = _read(
        """
        SELECT SUM(amount) total_amount,
               COUNT(DISTINCT student_id) active_students
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        """,
        {"start": prev_s, "end": prev_e},
    ).iloc[0]
    prev_lib = _read(
        """
        SELECT ROUND(SUM(stay_minutes) / NULLIF(COUNT(DISTINCT student_id), 0) / :days, 1) avg_daily_min
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        """,
        {"start": prev_s, "end": prev_e, "days": days},
    ).iloc[0]
    new_warn_prev = int(_read(
        "SELECT COUNT(*) n FROM warning WHERE warning_date >= :start AND warning_date <= :end",
        {"start": prev_s, "end": prev_e},
    ).iloc[0]["n"] or 0)
    prev_active_combined = int(_read(
        """
        SELECT COUNT(DISTINCT student_id) n FROM (
            SELECT student_id FROM consumption
            WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
            UNION
            SELECT student_id FROM library_record
            WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        ) t
        """,
        {"start": prev_s, "end": prev_e},
    ).iloc[0]["n"] or 0)

    # ---------- 计算占比与环比 ----------
    def pct(cur_v, prev_v):  # 环比 %，prev 为 0 则 None
        cv = float(cur_v or 0)
        pv = float(prev_v or 0)
        if pv == 0:
            return None
        return round((cv - pv) / pv * 100, 1)

    active_rate = round(active_combined / stu_total * 100, 1) if stu_total else 0.0
    prev_active_rate = round(prev_active_combined / stu_total * 100, 1) if stu_total else 0.0

    # ---------- 小泡图（每日聚合） ----------
    idx = pd.date_range(start=start, end=end, freq="D")
    spark_amount_df = _read(
        """
        SELECT DATE(consumed_at) d, ROUND(SUM(amount),2) v
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY d
        """,
        {"start": start, "end": end},
    )
    spark_library_df = _read(
        """
        SELECT DATE(gate_in_time) d, ROUND(SUM(stay_minutes),0) v
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY d
        """,
        {"start": start, "end": end},
    )
    spark_warning_df = _read(
        """
        SELECT warning_date d, COUNT(*) v
        FROM warning
        WHERE warning_date >= :start AND warning_date <= :end
        GROUP BY d
        """,
        {"start": start, "end": end},
    )

    def _spark(df, label_col="v"):
        if not len(df):
            return [0] * len(idx)
        series = df.set_index(pd.DatetimeIndex(pd.to_datetime(df["d"]))).reindex(idx, fill_value=0)
        return [round(float(x), 2) for x in series[label_col]]

    return {
        "window": [start, end],
        "prev_window": [prev_s, prev_e],
        "student_count": stu_total,
        "active_rate": active_rate,
        "total_amount": round(float(cur["total_amount"] or 0), 2),
        "avg_daily_study_minutes": float(cur_lib["avg_daily_min"] or 0),
        "warning_count": int(warn_row["n"] or 0),
        "warning_pending": int(warn_row["pending"] or 0),
        "amount_delta": pct(cur["total_amount"], prev["total_amount"]),
        "study_delta": pct(cur_lib["avg_daily_min"], prev_lib["avg_daily_min"]),
        "warning_delta": pct(new_warn_cur, new_warn_prev),
        "active_delta": round(active_rate - prev_active_rate, 1),
        "spark_amount": _spark(spark_amount_df),
        "spark_library": _spark(spark_library_df),
        "spark_warning": _spark(spark_warning_df),
    }
