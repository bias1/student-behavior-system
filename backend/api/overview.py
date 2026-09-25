# -*- coding: utf-8 -*-
"""
总览接口（群体概览大屏）
  GET /api/overview            核心指标卡
  GET /api/overview/groups     群体结构（学院/年级/专业/性别）
  GET /api/overview/rank       消费排行（order=asc 用于挑疑似低消费学生）
  GET /api/overview/meta       数据时间范围与字典，前端初始化用
"""

from __future__ import annotations

from flask import Blueprint, request

from analysis import statistics
from models import MERCHANT_TYPES, WARNING_LEVELS, WARNING_STATUS
from utils import data_range, fail, ok, parse_int, resolve_window

bp = Blueprint("overview", __name__, url_prefix="/api/overview")


@bp.get("/")
def get_overview():
    """总览指标：学生数、总消费、日均图书馆时长、预警数、行为高峰"""
    return ok(statistics.overview())


@bp.get("/summary")
def get_summary():
    """
    概览页汇总指标（包含环比/小泡图数据）。
    ?days=N (默认 30)  从数据右界往回推 N 天
    返回: active_rate / total_amount / warning_count / *_delta / spark_* 等
    """
    start, end, days = resolve_window()
    return ok(statistics.summary_metrics(start, end, days))


@bp.get("/groups")
def get_groups():
    """
    按维度看群体差异。dim 支持 college / grade / major / gender，
    非法值直接返回 400，避免前端传错导致图表空白难排查。
    """
    dim = request.args.get("dim", "college").lower()
    if dim not in {"college", "grade", "major", "gender"}:
        return fail(f"dim 只支持 college/grade/major/gender，收到 {dim}")
    start, end, _ = resolve_window()
    return ok({"dim": dim, "window": [start, end],
               "items": statistics.group_distribution(start, end, dim)})


@bp.get("/rank")
def get_rank():
    """消费排行榜：limit 上限 100，order=asc 时给出的是"消费最少"的学生"""
    start, end, _ = resolve_window()
    limit = parse_int("limit", 10, 1, 100)
    order = request.args.get("order", "desc")
    return ok({"window": [start, end], "order": order,
               "items": statistics.consumption_rank(start, end, limit, order)})


@bp.get("/meta")
def get_meta():
    """元信息：把数据可用区间与枚举字典一次性给前端，避免各处硬编码"""
    start, end = data_range()
    return ok({
        "date_start": str(start),
        "date_end": str(end),
        "merchant_types": MERCHANT_TYPES,
        "warning_status": WARNING_STATUS,
        "warning_levels": WARNING_LEVELS,
        "weekday_names": statistics.WEEKDAYS_CN,
        "dims": ["college", "grade", "major", "gender"],
    })
