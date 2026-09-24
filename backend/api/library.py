# -*- coding: utf-8 -*-
"""
图书馆相关接口
  GET /api/library/trend     人流量趋势（人次/独立人数/日均时长/总时长）
  GET /api/library/heatmap   星期 × 小时 进馆热力图（双高峰识别）
  GET /api/library/hours     小时边际分布 + 区域偏好
"""

from __future__ import annotations

from flask import Blueprint

from analysis import statistics
from utils import ok, resolve_window

bp = Blueprint("library", __name__, url_prefix="/api/library")


def _trend_payload(start: str, end: str, days: int) -> dict:
    data = statistics.library_trend(start, end)
    data.update({"window": [start, end], "days": days})
    return data


@bp.get("/trend")
def trend():
    """按天人流：一次查询同时给出趋势、热力矩阵与区域分布，减少大屏请求数"""
    start, end, days = resolve_window()
    return ok(_trend_payload(start, end, days))


@bp.get("/heatmap")
def heatmap():
    """进馆时段热力图（ECharts heatmap 直接可用的结构）"""
    start, end, days = resolve_window()
    data = _trend_payload(start, end, days)
    return ok({"window": [start, end], "days": days, **data["heatmap"]})


@bp.get("/hours")
def hours():
    """小时边际分布 + 常去区域 Top8"""
    start, end, days = resolve_window()
    data = _trend_payload(start, end, days)
    return ok({"window": [start, end], "days": days,
               "hour_dist": data["hour_dist"], "area_dist": data["area_dist"]})
