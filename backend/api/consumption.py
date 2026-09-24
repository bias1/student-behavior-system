# -*- coding: utf-8 -*-
"""
消费相关接口
  GET /api/consumption/trend     按天消费趋势（含周末标记、可与在馆时长叠加）
  GET /api/consumption/heatmap   星期 × 小时 消费时段热力图
  GET /api/consumption/category  消费类别占比（商户类型 / 餐段 / 商户排行）

公共参数：?start=YYYY-MM-DD&end=YYYY-MM-DD  或  ?days=30（不给则取全库区间）
"""

from __future__ import annotations

from flask import Blueprint

from analysis import statistics
from utils import ok, resolve_window

bp = Blueprint("consumption", __name__, url_prefix="/api/consumption")


@bp.get("/trend")
def trend():
    """按天聚合；缺失日期后端已补 0，前端可直接铺折线"""
    start, end, days = resolve_window()
    data = statistics.consumption_trend(start, end)
    data.update({"window": [start, end], "days": days})
    return ok(data)


@bp.get("/heatmap")
def heatmap():
    """
    热力图数据格式直接对齐 ECharts：data = [[小时, 星期序号, 值], ...]，
    同时给出 max，前端 visualMap 不用再自己算最大值。
    """
    start, end, days = resolve_window()
    data = statistics.consumption_heatmap(start, end)
    data.update({"window": [start, end], "days": days})
    return ok(data)


@bp.get("/category")
def category():
    """类别占比：饼图（商户类型/餐段）+ 条形图（Top 商户）"""
    start, end, days = resolve_window()
    data = statistics.consumption_category(start, end)
    data.update({"window": [start, end], "days": days})
    return ok(data)
