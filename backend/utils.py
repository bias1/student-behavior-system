# -*- coding: utf-8 -*-
"""
公共层：统一返回格式、JSON 序列化兼容、时间范围解析。

统一响应体：{ "code": 200, "data": ..., "msg": "success" }
"""

from __future__ import annotations

import datetime as dt
import decimal
import math
import time
from typing import Any, Dict, Optional, Tuple

from flask import Response, jsonify
from flask.json.provider import DefaultJSONProvider
from sqlalchemy import text

from models import db

SUCCESS = 200
# 业务错误码约定：4xx 客户端问题，5xx 服务端问题，5001 业务异常
ERR_PARAM = 400
ERR_NOT_FOUND = 404
ERR_SERVER = 500


# =============================================================================
# 1. JSON 序列化兼容：Decimal / numpy / date 都要能转成前端可用的值
# =============================================================================

class SafeJSONProvider(DefaultJSONProvider):
    """
    Flask 默认 JSONProvider 遇到 Decimal、numpy 类型会抛 TypeError。
    大屏接口大量返回聚合数值（MySQL DECIMAL、pandas numpy 标量），这里统一转换。
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (dt.datetime,)):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, (dt.date, dt.time)):
            return o.strftime("%Y-%m-%d" if isinstance(o, dt.date) else "%H:%M:%S")
        if isinstance(o, (dt.timedelta,)):
            return round(o.total_seconds() / 60)                 # 时长 -> 分钟
        if isinstance(o, float):
            # NaN/Inf 不是合法 JSON，前端 ECharts 会直接报错，统一转 None
            return None if (math.isnan(o) or math.isinf(o)) else o
        if hasattr(o, "item"):                                    # numpy 标量
            try:
                return o.item()
            except ValueError:
                return str(o)
        if hasattr(o, "tolist"):                                  # numpy 数组
            return o.tolist()
        return super().default(o)


def ok(data: Any = None, msg: str = "success") -> Response:
    """成功响应"""
    return jsonify({"code": SUCCESS, "data": data, "msg": msg})


def fail(msg: str = "参数错误", code: int = ERR_PARAM, data: Any = None) -> Response:
    """
    失败响应：HTTP 状态与 body.code 保持一致，
    这样前端 axios 拦截器既能按 HTTP 码统一处理，也能读 body 里的业务码。
    """
    resp = jsonify({"code": code, "data": data, "msg": msg})
    resp.status_code = code if 400 <= code < 600 else 500
    return resp


# =============================================================================
# 2. 参数解析与数据时间范围
# =============================================================================

def parse_int(name: str, default: int, min_val: int = 1, max_val: int = 100000) -> int:
    """从 query 取整数参数并夹在合法区间内，避免 ?days=-1 之类把 SQL 打挂"""
    from flask import request

    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(min_val, min(max_val, v))


def parse_date(name: str) -> Optional[dt.date]:
    from flask import request

    raw = request.args.get(name)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


_data_range_cache: Dict[str, Any] = {}


def data_range(refresh: bool = False) -> Tuple[dt.date, dt.date]:
    """
    取全库数据的起止日期（模拟数据是历史区间，不能用"今天"当默认右界）。
    结果缓存 5 分钟，避免每次请求都全表 MIN/MAX。
    """
    now = time.time()
    if not refresh and _data_range_cache.get("exp", 0) > now:
        return _data_range_cache["start"], _data_range_cache["end"]

    sql = text("SELECT MIN(DATE(consumed_at)) s, MAX(DATE(consumed_at)) e FROM consumption WHERE is_valid=1")
    with db.engine.connect() as conn:
        row = conn.execute(sql).mappings().first()
    start = (row or {}).get("s") or dt.date.today()
    end = (row or {}).get("e") or dt.date.today()
    _data_range_cache.update({"start": start, "end": end, "exp": now + 300})
    return start, end


def resolve_window(default_days: int = 30) -> Tuple[str, str, int]:
    """
    统一的时间窗口解析：
      ?start=2026-05-01&end=2026-05-20  优先
      ?days=30                          从数据右界往回推
    返回 (start_str, end_str, 实际天数)，字符串便于直接作为 SQL 绑定参数。
    """
    from flask import request

    d_start, d_end = data_range()          # 顺序不可写反：data_range 返回 (起, 止)
    start = parse_date("start") or (d_end - dt.timedelta(days=default_days - 1))
    end = parse_date("end") or d_end
    if request.args.get("days") and not parse_date("start"):
        days = parse_int("days", default_days, 1, 3650)
        start = max(d_start, d_end - dt.timedelta(days=days - 1))
        end = d_end
    if start > end:
        start, end = end, start
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), (end - start).days + 1


def df_records(df) -> list[dict]:
    """DataFrame -> list[dict]，同时把 numpy 标量转原生类型（配合 SafeJSONProvider）"""
    if df is None or len(df) == 0:
        return []
    return df.to_dict(orient="records")
