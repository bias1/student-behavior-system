# -*- coding: utf-8 -*-
"""
分析层：基于阈值的异常行为预警规则引擎（细粒度扩展规则集）

本模块是"扩展规则引擎"；毕设总纲要求的四大规则（连续无消费、本周消费骤降、
连续未进馆、夜间周频次）在 analysis/warning.py，那边带预警等级动态判定，
两边 rule_code 不重叠，可以分别扫描、互不覆盖。

规则参数全部来自 warning_rule 表（阈值外置，改参数不用改代码）：
  HIGH_CONSUME    单日消费绝对超限，或超过个人近 N 日均值 multiplier 倍
  LOW_CONSUME     连续 window_days 天每天交易笔数 <= max_meals_per_day（频次口径，非金额）
  NIGHT_CONSUME   深夜时段（start-end 跨零点）消费次数达到 times 次
  MEAL_IRREGULAR  近 window_days 天缺餐率超过 missing_rate
  NO_LIBRARY      连续 days 天无进馆记录（实现保留，由 analysis/warning.py 复用）
  OVERSTAY        单日在馆时长超过 hours 小时

实现要点：
1. 以"学生 × 日期"透视矩阵做滑动窗口判断，比在 Python 里逐人循环快几个数量级。
2. 写入用 INSERT ... ON DUPLICATE KEY UPDATE，配合唯一键
   (student_id, rule_code, warning_date) 实现幂等 —— 重复扫描不会产生重复预警。
3. 只统计 is_valid=1 的数据，脏数据不能触发预警。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sqlalchemy import text

from models import db

# rule_code -> 大类（与 warning_rule.warning_type 保持一致）
RULE_TYPE = {"HIGH_CONSUME": "consume", "LOW_CONSUME": "consume", "NIGHT_CONSUME": "consume",
             "MEAL_IRREGULAR": "health", "NO_LIBRARY": "study", "OVERSTAY": "study"}

_SNAPSHOT_READY = False


def ensure_snapshot_column() -> None:
    """
    老库自愈：给 warning 补 rule_name 快照列（审计问题：逻辑外键只保证历史记录不丢，
    但 to_dict 回查当前规则表，事后改名会"篡改"历史列表展示）。
    进程内探测一次；扫描写入前调用，对已有新库零成本。同时对历史空行做一次背靠填充。
    """
    global _SNAPSHOT_READY
    if _SNAPSHOT_READY:
        return
    with db.engine.begin() as conn:
        has = conn.execute(text("SHOW COLUMNS FROM warning LIKE 'rule_name'")).first()
        if not has:
            conn.execute(text("ALTER TABLE warning ADD COLUMN rule_name VARCHAR(80) NULL"
                              " COMMENT '规则名称快照（触发时）' AFTER rule_code"))
        conn.execute(text("UPDATE warning w JOIN warning_rule r ON w.rule_code = r.rule_code"
                          " SET w.rule_name = r.rule_name WHERE w.rule_name IS NULL"))
    _SNAPSHOT_READY = True


def _load_rules() -> Dict[str, Dict[str, Any]]:
    """读取启用的规则；缺失字段用默认值兜底，保证规则表被误改也不会崩"""
    df = pd.read_sql(text("SELECT rule_code, rule_name, warning_type, threshold_value, threshold_json,"
                          " warning_level, description FROM warning_rule WHERE enabled = 1"), con=db.engine)
    out = {}
    for _, r in df.iterrows():
        cfg = r["threshold_json"]
        if isinstance(cfg, str):
            cfg = json.loads(cfg or "{}")
        out[r["rule_code"]] = {
            "rule_name": r["rule_name"],
            "warning_type": r["warning_type"] or RULE_TYPE.get(r["rule_code"], "consume"),
            "threshold": float(r["threshold_value"]) if r["threshold_value"] is not None else None,
            "json": cfg or {},
            "level": int(r["warning_level"]),
            "description": r["description"] or "",
        }
    return out


def _daily_data(start: str, end: str, night_h0: int = 23, night_h1: int = 5) -> Dict[str, pd.DataFrame]:
    """
    一次把两张日聚合表取回来，所有规则复用，避免反复扫全表。
    深夜区间由参数控制，必须与 NIGHT_CONSUME 规则配置保持一致：
    之前写死 22 点而配置是 23 点，导致"预警文案说 23:00、实际按 22:00 统计"的口径错位。
    """
    cons = pd.read_sql(text("""
        SELECT student_id, DATE(consumed_at) AS d,
               SUM(amount) AS amt, COUNT(*) AS n,
               SUM(CASE WHEN HOUR(consumed_at) >= :h0 OR HOUR(consumed_at) < :h1 THEN 1 ELSE 0 END) AS night,
               SUM(meal_period = '早餐') AS b, SUM(meal_period = '午餐') AS l, SUM(meal_period = '晚餐') AS d2
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY student_id, d
        """), con=db.engine,
        params={"start": start, "end": end, "h0": night_h0, "h1": night_h1})

    lib = pd.read_sql(text("""
        SELECT student_id, DATE(gate_in_time) AS d, COUNT(*) AS visits, SUM(stay_minutes) AS mins
        FROM library_record
        WHERE is_valid = 1 AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY student_id, d
        """), con=db.engine, params={"start": start, "end": end})

    students = pd.read_sql(text("SELECT student_id, name FROM student"), con=db.engine)
    return {"cons": cons, "lib": lib, "students": students}


def _pivot(df: pd.DataFrame, values: str, dates: pd.DatetimeIndex, fill: float = 0.0) -> pd.DataFrame:
    """长表 -> (学生 × 日期) 宽表，缺日期补 fill（"没消费"本身就是 0 元这个信息）"""
    if len(df) == 0:
        return pd.DataFrame(0.0, index=pd.Index([], name="student_id"), columns=dates)
    p = df.pivot_table(index="student_id", columns=pd.to_datetime(df["d"]), values=values, aggfunc="sum")
    return p.reindex(columns=dates).fillna(fill)


def _melt(mask: pd.DataFrame, value_fn) -> List[Dict[str, Any]]:
    """布尔矩阵 -> 预警行列表；value_fn(student, date) 产出指标值与详情"""
    rows = []
    for sid, day in zip(*np.where(mask.to_numpy())):
        rows.append({"student_id": str(mask.index[sid]), "warning_date": mask.columns[day].date(),
                     **value_fn(str(mask.index[sid]), mask.columns[day].date())})
    return rows


# =============================================================================
# 各规则实现：统一返回 [{student_id, warning_date, metric_value, message, detail}]
# =============================================================================

def rule_high_consume(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    thr = cfg["threshold"] or 300.0
    mult = float(cfg["json"].get("multiplier", 3.0))
    amt = _pivot(data["cons"], "amt", dates)
    own = amt.replace(0, np.nan).mean(axis=1).fillna(0)          # 个人日均（不含 0 元日）
    over_abs = amt > thr
    # 相对个人基线：必须加括号，& 的优先级高于比较运算符，写错会变成对浮点数组做位运算
    over_rel = (amt > own.values[:, None] * mult) & (amt > thr * 0.4)
    mask = (over_abs | over_rel).fillna(False)

    def build(sid, d):
        v = float(amt.loc[sid, pd.Timestamp(d)])
        base = float(own[sid])
        ratio = round(v / base, 2) if base else None
        # 文案必须区分触发口径（审计发现的逻辑 Bug）：130 元只命中"个人基线 3 倍"分支时，
        # 写"超过阈值 300 元"是错的；两种口径的处置建议也不同（偶发采购 vs 消费习惯突变）
        if v > thr:
            msg = f"{d} 单日消费 {v:.2f} 元，超过绝对阈值 {thr:.0f} 元（个人日均 {base:.2f} 元）"
            trigger = "absolute"
        else:
            msg = (f"{d} 单日消费 {v:.2f} 元，达个人日均 {base:.2f} 元的 {ratio or 0:.1f} 倍"
                   f"（基线倍数 {mult:.0f}，未超绝对阈值 {thr:.0f} 元）")
            trigger = "relative"
        return {"metric_value": round(v, 2), "message": msg,
                "detail": {"day_amount": round(v, 2), "own_avg": round(base, 2),
                           "ratio": ratio, "threshold": thr, "multiplier": mult,
                           "trigger": trigger}}
    return _melt(mask, build)


def _rolling_all(flag: pd.DataFrame, win: int) -> pd.DataFrame:
    """
    沿"日期"方向做滑动窗口计数（连续 win 天都为 True 才置 True）。
    pandas 2.x 已移除 rolling(axis=1)，这里用转置实现行向窗口。
    """
    return flag.T.rolling(win).sum().T >= win


def rule_low_consume(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    """
    疑似节食/经济困难：连续 window_days 天、每天交易笔数 <= max_meals_per_day。

    口径为什么要改（实测驱动，非拍脑袋）：
      旧实现是 (日金额 < threshold) 或 (日笔数 <= max_meals) 的 OR，窗口 3 天。
      在 200 人 / 30 天数据上实测命中 66 人（占 33%），逐一对账 ground truth 后发现：
      真正注入的节食样本只有 5 人，其余 61 个都是"周五晚~周日"离校造成的连续零消费日
      —— 0 元日既满足 amt<10 又满足 n<=1，被这条规则误抓。而"整天零消费"本就是
      总纲规则 NO_CONSUME 的管辖范围，两条规则严重重叠。
      曾尝试改判为"消费额低于自身基线"，实测召回直接掉到 2/5：节食样本的低消费日往往是
      一笔正常单价的早餐(6元)/超市(22元)，金额并不低于个人均值——真正稳定的信号是
      "笔数/频次"而不是"金额"。最终按数据分布重新定标：
        1) 去掉金额 OR 分支（它对 0 笔日恒真，是误报主因）；
        2) 窗口从 3 天提到 4 天：周末至多 2~3 天连零，4 天连续才能把"度周末"与"持续节食"分开；
           实测 win=4 时注入的 5 名样本仍 5/5 召回，win=5 起召回崩到 3/5（节食段仅 4~6 天且含零消费空洞）；
        3) 只对"连续段首日"出单，消除段内逐日刷屏（186 条 -> 每人一次）；
        4) 整窗口都低的学生更像已离校，排除出去交给 NO_CONSUME，不在此重复告警。
      触发条件是绝对频次，但文案回带"本人平时日均笔数"作为个人基线参照，体现"相对自身"。
    已知局限（论文里如实写）：只买多笔极小额（如一天两笔各 2 元）的学生 n>1 会漏判，
      这类形态与"正常加餐"在卡数据上不可分，宁缺毋滥。
    """
    win = int(cfg["json"].get("window_days", 4))
    max_meals = int(cfg["json"].get("max_meals_per_day", 1))
    amt = _pivot(data["cons"], "amt", dates)
    n = _pivot(data["cons"], "n", dates)
    # 个人平时日均笔数（只统计有消费的天），仅作文案里的"相对自身"参照，不参与触发
    own_n = n.where(n > 0).mean(axis=1)
    hit = _rolling_all(n <= max_meals, win)               # 连续 win 天每天 <= max_meals 笔
    win_total = n.T.rolling(win).sum().T                   # 窗口内总笔数（轴同 _rolling_all）
    # 段首日：前一天还不满足、今天满足 => 一段低消费的开始（避免段内每天重复出单）
    start = hit & ~hit.shift(1, axis=1).fillna(False)
    all_low = (n <= max_meals).all(axis=1)                # 整窗口都低 -> 归 NO_CONSUME
    # win_total>=1：把"窗口内完全零消费"判给 NO_CONSUME，本规则只抓"买了但买得极少"
    mask = (start & (win_total >= 1) & ~all_low.values[:, None]).fillna(False)

    def build(sid, d):
        ts = pd.Timestamp(d)
        w = amt.loc[sid, ts - pd.Timedelta(days=win - 1):ts]
        wn = n.loc[sid, ts - pd.Timedelta(days=win - 1):ts]
        avg = float(w.sum()) / win
        meals = float(wn.sum()) / win
        base = float(own_n[sid]) if sid in own_n.index else 0.0
        return {"metric_value": round(avg, 2),
                "message": f"{w.index[0].date()} 起连续 {win} 天每天消费不超过 {max_meals} 笔"
                           f"（日均 {meals:.1f} 笔、{avg:.1f} 元，本人平时约 {base:.1f} 笔/天），疑似节食或经济困难",
                "detail": {"window_days": win, "max_meals_per_day": max_meals,
                           "meals_per_day": round(meals, 2), "daily_avg": round(avg, 2),
                           "window_total": round(float(w.sum()), 2),
                           "own_daily_meals_baseline": round(base, 2),
                           "dates": [str(x.date()) for x in w.index]}}
    return _melt(mask, build)


def _night_hours(cfg: Dict) -> tuple:
    """把配置里的 "23:00"/"05:00" 解析成小时整数；非法值退回默认，不让规则因为配置写错而崩"""
    def _h(raw, default):
        try:
            return max(0, min(23, int(str(raw).split(":")[0])))
        except (ValueError, TypeError):
            return default
    j = cfg.get("json") or {}
    return _h(j.get("start", "23:00"), 23), _h(j.get("end", "05:00"), 5)


def rule_night_consume(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    times = int(cfg["json"].get("times", 3))
    h0, h1 = _night_hours(cfg)
    night = _pivot(data["cons"], "night", dates)
    total = night.sum(axis=1)                       # 统计窗口内深夜消费累计次数（口径随分析窗口，不是自然月）
    hit = total[total >= times]
    if hit.empty:
        return []
    rows = []
    name = f"{h0:02d}:00-{h1:02d}:00"               # 用实际参与统计的区间拼文案，避免口径歧义
    last_night = night[night > 0]
    for sid, v in hit.items():
        last = last_night.loc[sid].index.max() if len(last_night.loc[sid]) else dates[-1]
        rows.append({"student_id": str(sid), "warning_date": pd.Timestamp(last).date(),
                     "metric_value": round(float(v), 2),
                     "message": f"{name} 时段累计消费 {int(v)} 次（阈值 {times} 次），作息异常",
                     "detail": {"night_times": int(v), "window": name, "threshold": times}})
    return rows


def rule_meal_irregular(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    rate_thr = float(cfg["json"].get("missing_rate", 0.5))
    win = int(cfg["json"].get("window_days", 7))
    cons = data["cons"].copy()
    # 当天覆盖了几个正餐段（0~3），未出现的日期记 0 -> 缺餐率 = 1 - 均值/3
    cons["meals"] = (cons[["b", "l", "d2"]] > 0).sum(axis=1)
    meals = _pivot(cons, "meals", dates)
    window = meals.iloc[:, -win:] if len(meals.columns) >= win else meals
    rate = (1 - window.mean(axis=1) / 3).clip(0, 1)
    hit = rate[rate > rate_thr]
    return [{
        "student_id": str(sid), "warning_date": dates[-1].date(), "metric_value": round(float(v) * 100, 2),
        "message": f"近 {win} 天缺餐率 {v * 100:.1f}%（阈值 {rate_thr * 100:.0f}%），三餐不规律",
        "detail": {"window_days": win, "missing_rate": round(float(v) * 100, 2),
                   "avg_meals": round(float(meals.iloc[:, -win:].mean(axis=1)[sid]), 2)}
    } for sid, v in hit.items()]


def rule_no_library(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    days = int(cfg["threshold"] or cfg["json"].get("days", 30))
    lib = data["lib"]
    last = (pd.to_datetime(lib["d"]).groupby(lib["student_id"].values).max() if len(lib)
            else pd.Series(dtype="datetime64[ns]"))
    # 窗口开始前的最后一次进馆（审计发现的窗口边界问题）：data["lib"] 只含窗口内记录，
    # "窗口前几周刚进过馆"与"从没进过馆"会被混成同一种"窗口内无记录"，
    # 连续天数被截断成窗口长度。补查一次窗口前的 MAX，才能报出真实间隔。
    prev = pd.read_sql(text(
        "SELECT student_id, MAX(DATE(gate_in_time)) AS d FROM library_record"
        " WHERE is_valid = 1 AND gate_in_time < :start GROUP BY student_id"),
        con=db.engine, params={"start": str(dates[0].date())})
    prev_last = pd.Series(pd.to_datetime(prev["d"]).values, index=prev["student_id"].values) \
        if len(prev) else pd.Series(dtype="datetime64[ns]")
    all_students = data["students"]["student_id"].tolist()
    rows = []
    for sid in all_students:
        if sid in last.index:
            ref, in_window = last[sid], True
        elif sid in prev_last.index:
            ref, in_window = prev_last[sid], False
        else:
            ref, in_window = None, False
        gap = (dates[-1] - ref).days if ref is not None else len(dates)
        if gap >= days:
            rows.append({"student_id": sid, "warning_date": dates[-1].date(), "metric_value": float(gap),
                         "message": f"已连续 {gap} 天无进馆记录（阈值 {days} 天），学习行为异常"
                                    + ("" if in_window or ref is None else f"，末次进馆 {ref.date()}"),
                         "detail": {"gap_days": int(gap), "threshold_days": days,
                                    "last_visit": str(ref.date()) if ref is not None else None}})
    return rows


def rule_overstay(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    hours = float(cfg["threshold"] or cfg["json"].get("hours", 12))
    mins = _pivot(data["lib"], "mins", dates)
    mask = (mins > hours * 60).fillna(False)

    def build(sid, d):
        v = float(mins.loc[sid, pd.Timestamp(d)])
        return {"metric_value": round(v / 60, 2),
                "message": f"{d} 在馆 {v / 60:.1f} 小时（阈值 {hours:.0f} 小时），久坐需提醒",
                "detail": {"stay_minutes": round(v, 0), "threshold_hours": hours}}
    return _melt(mask, build)


RULE_FUNCS = {
    "HIGH_CONSUME": rule_high_consume,
    "LOW_CONSUME": rule_low_consume,
    "NIGHT_CONSUME": rule_night_consume,
    "MEAL_IRREGULAR": rule_meal_irregular,
    "OVERSTAY": rule_overstay,
    # NO_LIBRARY 故意不注册：它属于毕设总纲四大规则，由 analysis/warning.py 统一产出
    # （那边要在检测结果上叠加"7-13 天中、>=14 天高"的等级浮动）。
    # 检测函数 rule_no_library 保留在下面供 warning.py 复用，避免出现两份实现或
    # 同一 rule_code 被两个引擎各写一遍导致等级口径漂移。
}


# =============================================================================
# 扫描入口
# =============================================================================

def scan(start: str, end: str, rules: List[str] | None = None) -> Dict[str, Any]:
    """
    执行规则扫描并落库。
    同一 (学生, 规则, 日期) 只保留一条，重复执行只更新数值，不产生重复预警。
    """
    rules_cfg = _load_rules()
    ensure_snapshot_column()             # 写入前先保证 rule_name 快照列存在（老库自愈）
    # 深夜口径只有一处定义：从 NIGHT_CONSUME 配置读出小时区间，再取数，避免规则与 SQL 各说各话
    n0, n1 = _night_hours(rules_cfg.get("NIGHT_CONSUME", {"json": {}}))
    data = _daily_data(start, end, n0, n1)
    dates = pd.date_range(start=start, end=end, freq="D")
    if len(dates) == 0:
        return {"written": 0, "by_rule": {}, "msg": "时间窗口内无数据"}

    rows: List[Dict[str, Any]] = []
    by_rule: Dict[str, int] = {}
    for code, fn in RULE_FUNCS.items():
        if code not in rules_cfg or (rules and code not in rules):
            continue
        hits = fn(data, dates, rules_cfg[code])
        by_rule[code] = len(hits)
        tinfo = rules_cfg[code]
        for h in hits:
            rows.append({
                "student_id": h["student_id"], "rule_code": code,
                # 触发时的规则名随记入库，事后改名不回溯历史列表
                "rule_name": tinfo["rule_name"],
                "warning_type": tinfo["warning_type"], "warning_level": tinfo["level"],
                "warning_date": h["warning_date"], "metric_value": h.get("metric_value"),
                "detail_json": json.dumps(h.get("detail", {}), ensure_ascii=False, default=str),
                "message": h["message"][:255], "status": 0,
            })

    written = 0
    if rows:
        # 唯一键幂等：重复扫描更新指标与文案，已人工处理过的不改状态（保留处置痕迹）
        sql = text("""
            INSERT INTO warning (student_id, rule_code, rule_name, warning_type, warning_level, warning_date,
                                 metric_value, detail_json, message, status)
            VALUES (:student_id, :rule_code, :rule_name, :warning_type, :warning_level, :warning_date,
                    :metric_value, :detail_json, :message, 0)
            ON DUPLICATE KEY UPDATE metric_value = VALUES(metric_value),
                                    message = VALUES(message),
                                    detail_json = VALUES(detail_json),
                                    rule_name = VALUES(rule_name),
                                    warning_level = VALUES(warning_level)
            """)
        with db.engine.begin() as conn:
            conn.execute(sql, rows)          # executemany：一次性批量写
        written = len(rows)

    return {
        "written": written,
        "by_rule": by_rule,
        "window": [start, end],
        "rules_enabled": [c for c in rules_cfg if not rules or c in rules],
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
