# -*- coding: utf-8 -*-
"""
分析层：毕设总纲四大预警规则（含预警等级动态判定）

规则与口径（rule_code 与 warning_rule 表严格对应）：
  W1  NO_CONSUME          连续 >=3 天无消费记录              -> 消费异常   级别：>=5 天高 / 3-4 天中
  W2  CONSUME_DROP        本自然周消费额 < 上一周 50%         -> 消费骤降   级别：降幅>=75% 高 / 50-75% 中
  W3  NO_LIBRARY          连续 >=7 天无进馆记录              -> 学习异常   级别：>=14 天高 / 7-13 天中
  W4  NIGHT_WEEK_CONSUME  自然周内夜间(23:00-05:00)消费 >5 次 -> 作息异常   级别：>=10 次高 / 6-9 次中

连续型规则（W1/W3）在"里程碑日"出单：达到阈值当天一条、跨到高线当天再一条，
等级表达严重程度，不靠刷屏条数表达 —— 详见 rule_no_consume 注释。

与 analysis/warning_rules.py 的分工（重要，别搞混）：
  - 本文件实现"总纲口径"的四条规则：判定简单、可解释、等级随严重程度浮动；
  - warning_rules.py 是补充的细粒度规则（单日超额 HIGH_CONSUME、疑似节食 LOW_CONSUME、
    深夜累计 NIGHT_CONSUME、缺餐率 MEAL_IRREGULAR、久坐 OVERSTAY），等级取配置表静态值；
  - 两边 rule_code 不重叠，可分别扫描、互不覆盖。唯一重名的 NO_LIBRARY 已只由本文件产出
    （warning_rules 中的检测函数保留但注销注册，这里复用其算法再叠加等级），
    否则同一规则被两个引擎各写一遍，会出现"等级一会儿 1 一会儿 3"的口径漂移。

设计约束（都是踩过的坑）：
  1. "自然周"以周一为起点自行推导，不用 pandas 的 to_period('W')（它的锚点是周日，
     跨库/跨版本容易把周一算进上一周，导致"本周"只有 6 天而与上周不可比）。
  2. 只比较**完整周**：窗口首日所在的残缺周、窗口末日所在的残缺周全部丢弃，
     否则 3 天的"本周"必然低于 7 天的"上周"，规则会全员误报。
  3. 骤降要设基数下限：上周只花了 12 元的学生，本周 5 元也满足"<50%"，但这不是经济困难。
  4. 夜间时段（23:00-05:00）必须与聚类特征 night_ratio、个体画像 night_times 同口径，
     统一从规则配置解析小时区间再下推到 SQL，不在本文件写死。
  5. 全程只统计 is_valid=1 的数据；落库靠唯一键 (student_id, rule_code, warning_date) 幂等。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import bindparam, text

from analysis import warning_rules as ext  # 复用已校准的检测函数，不重复实现
from models import db

# 总纲四大规则的默认配置：DB 里有同码记录则以 DB 为准（阈值外置，改参数不改代码）
SYLLABUS_RULES: Dict[str, Dict[str, Any]] = {
    "NO_CONSUME": {
        "rule_name": "连续无消费", "warning_type": "consume",
        "threshold_value": 3.00,
        "threshold_json": {"days": 3, "level_high_days": 5},
        "warning_level": 2,
        "description": "连续 3 天无任何消费记录（>=5 天升级为高），疑似离校、经济困难或卡片异常",
    },
    "CONSUME_DROP": {
        "rule_name": "本周消费骤降", "warning_type": "consume",
        "threshold_value": 0.50,
        "threshold_json": {"ratio": 0.5, "level_high_ratio": 0.25, "min_last_week_amount": 30.0},
        "warning_level": 2,
        "description": "自然周消费额不足上周 50%（降幅 >=75% 升级为高），且上周消费不低于 30 元",
    },
    "NO_LIBRARY": {
        "rule_name": "长期未进图书馆", "warning_type": "study",
        "threshold_value": 7.00,
        "threshold_json": {"days": 7, "level_high_days": 14},
        "warning_level": 2,
        "description": "连续 7 天无进馆记录（>=14 天升级为高），学习行为异常",
    },
    "NIGHT_WEEK_CONSUME": {
        "rule_name": "夜间消费频发", "warning_type": "health",
        "threshold_value": 5.00,
        "threshold_json": {"start": "23:00", "end": "05:00", "times": 5, "level_high_times": 10},
        "warning_level": 2,
        "description": "单个自然周内 23:00-05:00 消费超过 5 次（>=10 次升级为高），作息异常",
    },
}

RULE_ORDER = list(SYLLABUS_RULES)   # 输出与文档展示保持固定顺序


# =============================================================================
# 规则配置：读取 + 幂等补齐（老库不用重建表）
# =============================================================================

def ensure_rules() -> int:
    """
    把总纲四大规则补写进 warning_rule（存在则只补齐描述，不覆盖人工调过的阈值）。
    扫描入口每次调用，保证接口层拿得到配置；INSERT IGNORE 让它对已有配置完全无损。
    """
    ext.ensure_snapshot_column()           # warning.rule_name 快照列自愈迁移（老库无需重建）
    rows = [{"code": code, **cfg} for code, cfg in SYLLABUS_RULES.items()]
    sql = text("""
        INSERT IGNORE INTO warning_rule (rule_code, rule_name, warning_type,
                                         threshold_value, threshold_json, warning_level, description)
        VALUES (:code, :rule_name, :warning_type, :threshold_value, :threshold_json,
                :warning_level, :description)
        """)
    # 历史口径校正：NIGHT_CONSUME 描述曾写"月内 ≥3 次"，实际实现是"分析窗口内累计"
    # （文案与算法口径不一致是审计点名的问题）；只命中旧文案，不覆盖管理员改过的描述。
    night_fix = text("UPDATE warning_rule SET description = :d"
                     " WHERE rule_code = 'NIGHT_CONSUME' AND description LIKE '%月内%'")
    with db.engine.begin() as conn:
        res = conn.execute(sql, [{"code": r["code"], "rule_name": r["rule_name"],
                                  "warning_type": r["warning_type"],
                                  "threshold_value": r["threshold_value"],
                                  "threshold_json": json.dumps(r["threshold_json"], ensure_ascii=False),
                                  "warning_level": r["warning_level"],
                                  "description": r["description"]} for r in rows])
        conn.execute(night_fix, {"d": "23:00-05:00 时段消费在分析窗口内累计 ≥3 次"})
        return int(res.rowcount or 0)


def load_config(codes: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    取规则配置：DB 值覆盖代码默认值，只保留 enabled=1 的规则。
    DB 里没记录的规则直接用默认值 —— 这样即使忘记执行 INSERT，规则也不会静默失效。
    """
    want = list(codes or RULE_ORDER)
    out: Dict[str, Dict[str, Any]] = {}
    for code in want:
        default = SYLLABUS_RULES.get(code)
        if default is None:
            continue
        cfg = {**default, "threshold_json": dict(default["threshold_json"])}
        row = pd.read_sql(text(
            "SELECT rule_name, warning_type, threshold_value, threshold_json, warning_level, enabled"
            " FROM warning_rule WHERE rule_code = :c"), con=db.engine, params={"c": code})
        if len(row):
            r = row.iloc[0]
            if int(r["enabled"]) != 1:
                continue                                   # 已被人工停用，尊重配置
            cfg["enabled_by_admin"] = True
            cfg["rule_name"] = r["rule_name"] or cfg["rule_name"]
            cfg["warning_type"] = r["warning_type"] or cfg["warning_type"]
            cfg["threshold"] = float(r["threshold_value"]) if r["threshold_value"] is not None \
                else float(cfg["threshold_value"])
            cfg["warning_level"] = int(r["warning_level"])
            j = r["threshold_json"]
            if isinstance(j, str):
                j = json.loads(j or "{}")
            cfg["threshold_json"] = {**cfg["threshold_json"], **(j or {})}
        else:
            cfg["threshold"] = float(cfg["threshold_value"])
        out[code] = cfg
    return out


# =============================================================================
# 通用小工具（pandas 规则判断的地基）
# =============================================================================

def _week_start(dates: pd.Series) -> pd.Series:
    """把任意日期序列映射到所在自然周的周一（中国口径一周之始）"""
    dts = pd.to_datetime(dates)
    return (dts - pd.to_timedelta(dts.dt.weekday, unit="D")).dt.normalize()


def _complete_weeks(start: str, end: str) -> List[pd.Timestamp]:
    """
    列出窗口内**完整覆盖**的自然周（返回各周的周一）。
    残缺周直接丢弃：只有 2 天的"本周"和 7 天的"上周"比值必然 <0.5，是纯误报源。
    """
    s, e = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    first = s - pd.Timedelta(days=int(s.dayofweek))        # 窗口首日所在周的周一（可能早于窗口）
    weeks = []
    ws = first
    while ws + pd.Timedelta(days=6) <= e:                  # 右界：周日必须落在窗口内
        if ws >= s:                                        # 左界：周一不能早于窗口起点，否则是残缺周
            weeks.append(ws)
        ws += pd.Timedelta(days=7)
    return weeks


def _streak(flag: pd.DataFrame) -> pd.DataFrame:
    """
    布尔矩阵(学生 × 日期) -> "截至当日连续 True 的天数"矩阵。
    200 人 × 90 天用一次行内循环即可（1.8 万次比较），比逐学生筛 DataFrame 快两个量级；
    pandas 没有原生的行向连续计数，rolling().sum() 只能算窗口内个数、算不了"连续段长度"。
    """
    a = flag.to_numpy().astype(bool)
    out = np.zeros(a.shape, dtype=np.int32)
    for i in range(a.shape[0]):
        run = 0
        for j in range(a.shape[1]):
            run = run + 1 if a[i, j] else 0
            out[i, j] = run
    return pd.DataFrame(out, index=flag.index, columns=flag.columns)


def _night_hours(cfg: Dict[str, Any]) -> tuple:
    """
    夜间时段口径只有一处定义：从规则配置解出 start/end，再交给扩展模块的同名函数，
    保证“周频次”与“窗口累计”两条夜间规则统计的是同一个时间段。
    （扩展层配置键叫 json，本层叫 threshold_json，这里做一次兼容转换）
    """
    cfg = cfg or {}
    j = cfg.get("threshold_json") or cfg.get("json") or {}
    return ext._night_hours({"json": j})


# =============================================================================
# 规则 1：连续 N 天无消费记录（消费异常）
# =============================================================================

def rule_no_consume(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    days = int(cfg["threshold"] or cfg["threshold_json"]["days"])
    # 高线必须严格高于阈值：否则配置写反（如 days=7/level_high_days=5）时，
    # 未达阈值的天数也会命中 milestone，把没异常的学生报成高级预警
    high_days = max(days + 1, int(cfg["threshold_json"].get("level_high_days", days + 2)))

    cnt = ext._pivot(data["cons"], "n", dates)             # 当天消费笔数，无记录日补 0
    zero_run = _streak(cnt <= 0)                           # 连续"零消费"天数
    # 只取"里程碑日"：刚达阈值那天（中）与刚达到高线那天（高）。
    # 段内每天都出一条的话，一个 7 天假期会连生 5 条记录，把预警列表和统计图
    # 全稀释成单一规则的刷屏；而等级已体现在"升级"那条上，逐日重复不增加信息量。
    milestone = (zero_run == days) | (zero_run == high_days)
    mask = milestone & (zero_run < len(dates))             # 整窗口都为 0 的不算（见下方说明）
    rows: List[Dict[str, Any]] = []
    for si, di in zip(*np.where(mask.to_numpy())):
        sid = str(cnt.index[si])
        d = cnt.columns[di].date()
        run = int(zero_run.to_numpy()[si, di])
        rows.append({
            "student_id": sid,
            "warning_date": d,                             # 触发日 = 连续段最后一天
            "metric_value": float(run),
            "warning_level": 3 if run >= high_days else 2, # >=high 天为高，其余为中
            "message": f"{sid} 自 {cnt.columns[di - run + 1].date()} 起已连续 {run} 天无消费记录"
                       f"（阈值 {days} 天），消费异常",
            "detail": {"streak_days": run, "threshold_days": days,
                       "level_high_days": high_days,
                       "last_consume_date": str(cnt.columns[di - run].date()) if di - run >= 0 else None,
                       "window_days": len(dates)},
        })
    return rows

# 说明：(zero_run < len(dates)) 这一条把"整个统计窗口一次消费都没有"的学生排除在外。
# 这类学生在数据上无法区分"真异常"与"已离校/卡片挂失/未接入采集"，
# 交给学籍状态与数据质量核查处理，比塞进预警列表更负责；论文里也要如实说明这条排除规则。
# 如果确实需要"持续异常每天推一条"的语义（短信日推场景），把 milestone 换回
# (zero_run >= days) 即可，唯一键 (student_id, rule_code, warning_date) 两种都能保证幂等。


# =============================================================================
# 规则 2：本自然周消费额 < 上一周 50%（消费骤降）
# =============================================================================

def rule_consume_drop(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    j = cfg["threshold_json"]
    ratio_thr = float(cfg["threshold"] or j.get("ratio", 0.5))
    high_ratio = float(j.get("level_high_ratio", ratio_thr / 2))   # 降幅更大才升级
    high_ratio = min(high_ratio, ratio_thr)      # 同理：高线不能高于阈值，否则命中即高级
    min_base = float(j.get("min_last_week_amount", 30.0))          # 基数下限，防小金额误报

    cons = data["cons"]
    if len(cons) == 0:
        return []
    df = cons[["student_id", "d", "amt"]].copy()
    df["week"] = _week_start(df["d"])
    wk = df.pivot_table(index="student_id", columns="week", values="amt", aggfunc="sum")

    weeks_all = _complete_weeks(str(dates[0].date()), str(dates[-1].date()))
    # 把列补齐到“窗口内全部完整周”：某周全员无消费时 pivot_table 根本不会出现这一列，
    # 不补列就会整周被跳过，恰好漏掉“骤降到 0”这一类最严重的样本
    wk = wk.reindex(columns=weeks_all)
    if len(weeks_all) < 2:
        return []                                   # 不足两个完整周，无法做周环比

    weeks = weeks_all
    out: List[Dict[str, Any]] = []
    for cur, prev in zip(weeks[1:], weeks[:-1]):
        cur_amt = wk[cur].fillna(0.0)
        prev_amt = wk[prev].fillna(0.0)
        hit = (prev_amt >= min_base) & (cur_amt < prev_amt * ratio_thr)
        for sid in hit[hit].index:
            p, c = float(prev_amt[sid]), float(cur_amt[sid])
            ratio = c / p if p else 0.0
            drop = (1 - ratio) * 100
            out.append({
                "student_id": str(sid),
                "warning_date": (cur + pd.Timedelta(days=6)).date(),   # 触发日 = 本周末（周日）
                "metric_value": round(ratio, 4),
                "warning_level": 3 if ratio <= high_ratio else 2,
                "message": f"{sid} 本周（{cur.date()}~{(cur + pd.Timedelta(days=6)).date()}）消费 {c:.2f} 元，"
                           f"仅为上周 {p:.2f} 元的 {ratio * 100:.1f}%（降幅 {drop:.1f}%），消费骤降",
                "detail": {"this_week": round(c, 2), "last_week": round(p, 2),
                           "ratio": round(ratio, 4), "drop_pct": round(drop, 2),
                           "this_week_start": str(cur.date()), "last_week_start": str(prev.date()),
                           "threshold_ratio": ratio_thr, "level_high_ratio": high_ratio,
                           "min_last_week_amount": min_base},
            })
    return out


# =============================================================================
# 规则 3：连续 N 天无进馆记录（学习异常）
# =============================================================================

def rule_no_library(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    """
    检测逻辑复用 warning_rules.rule_no_library（已按数据分布校准过 7 天阈值），
    这里只补总纲要求的"等级浮动"：>=14 天为高、7-13 天为中。
    """
    j = cfg["threshold_json"]
    days = int(cfg["threshold"] or j.get("days", 7))
    high_days = max(days + 1, int(j.get("level_high_days", days * 2)))   # 高线不能低于阈值
    sub = {"threshold": float(days), "json": {"days": days}}   # 传给扩展层，保持同口径
    rows = []
    for h in ext.rule_no_library(data, dates, sub):
        gap = int(h["detail"]["gap_days"])
        level = 3 if gap >= high_days else 2
        rows.append({**h, "warning_level": level,
                     "detail": {**h["detail"], "threshold_days": days, "level_high_days": high_days}})
    return rows


# =============================================================================
# 规则 4：自然周内夜间消费次数 > N（作息异常）
# =============================================================================

def rule_night_week(data: Dict[str, pd.DataFrame], dates: pd.DatetimeIndex, cfg: Dict) -> List[Dict]:
    j = cfg["threshold_json"]
    times = int(j.get("times", int(cfg["threshold"] or 5)))
    high_times = max(times + 1, int(j.get("level_high_times", times * 2)))   # 高线不能低于阈值
    h0, h1 = _night_hours(cfg)

    cons = data["cons"]
    if len(cons) == 0 or "night" not in cons.columns:
        return []
    df = cons[["student_id", "d", "night"]].copy()
    df["week"] = _week_start(df["d"])
    wk = df.pivot_table(index="student_id", columns="week", values="night", aggfunc="sum")

    weeks_all = _complete_weeks(str(dates[0].date()), str(dates[-1].date()))
    wk = wk.reindex(columns=weeks_all).fillna(0.0)
    if not weeks_all:
        return []

    name = f"{h0:02d}:00-{h1:02d}:00"
    out: List[Dict[str, Any]] = []
    for w in weeks_all:
        series = wk[w].fillna(0.0)
        hit = series[series > times]
        for sid, v in hit.items():
            v = int(v)
            out.append({
                "student_id": str(sid),
                "warning_date": (w + pd.Timedelta(days=6)).date(),
                "metric_value": float(v),
                "warning_level": 3 if v >= high_times else 2,
                "message": f"{sid} 本周（{w.date()} 起）{name} 时段消费 {v} 次"
                           f"（阈值 >{times} 次），夜间活动频发、作息异常",
                "detail": {"week_times": v, "threshold_times": times, "level_high_times": high_times,
                           "window": name, "week_start": str(w.date())},
            })
    return out


SYLLABUS_FUNCS = {
    "NO_CONSUME": rule_no_consume,
    "CONSUME_DROP": rule_consume_drop,
    "NO_LIBRARY": rule_no_library,
    "NIGHT_WEEK_CONSUME": rule_night_week,
}


# =============================================================================
# 扫描 / 落库 / 重算
# =============================================================================

def _persist(rows: List[Dict[str, Any]]) -> int:
    """
    幂等写库：唯一键 (student_id, rule_code, warning_date) 冲突时只更新指标/文案/等级，
    不改 status —— 人工处置过的记录必须留痕，重扫不能把"已处理"冲回"未处理"。
    """
    if not rows:
        return 0
    sql = text("""
        INSERT INTO warning (student_id, rule_code, rule_name, warning_type, warning_level, warning_date,
                             metric_value, detail_json, message, status)
        VALUES (:student_id, :rule_code, :rule_name, :warning_type, :warning_level, :warning_date,
                :metric_value, :detail_json, :message, 0)
        ON DUPLICATE KEY UPDATE metric_value = VALUES(metric_value),
                                message = VALUES(message),
                                detail_json = VALUES(detail_json),
                                rule_name = VALUES(rule_name),
                                warning_level = VALUES(warning_level),
                                warning_type = VALUES(warning_type)
        """)
    payload = []
    for r in rows:
        r = dict(r)
        detail = r.pop("detail", {})                       # 只留 SQL 绑定需要的键，多余键会被驱动拒收
        r["detail_json"] = json.dumps(detail, ensure_ascii=False, default=str)
        payload.append(r)
    with db.engine.begin() as conn:
        conn.execute(sql, payload)
    return len(payload)


def scan(start: str, end: str, rules: Optional[List[str]] = None,
         persist: bool = True) -> Dict[str, Any]:
    """
    执行总纲四大规则扫描。
      rules   限定只跑某些规则（rule_code 列表），None = 全部启用的
      persist False 则只实时计算并返回结果、不落库（答辩现场"看数不落库"、单元测试都靠它）
    """
    ensure_rules()
    cfgs = load_config(rules)
    if not cfgs:
        return {"written": 0, "by_rule": {}, "items": [], "msg": "没有启用的总纲规则"}

    # 深夜口径从配置里解析后再下推 SQL，与扩展引擎共用一份取数逻辑
    night_cfg = cfgs.get("NIGHT_WEEK_CONSUME") or \
        {"threshold_json": SYLLABUS_RULES["NIGHT_WEEK_CONSUME"]["threshold_json"]}
    n0, n1 = _night_hours(night_cfg)
    data = ext._daily_data(start, end, n0, n1)
    dates = pd.date_range(start=start, end=end, freq="D")
    if len(dates) == 0:
        return {"written": 0, "by_rule": {}, "items": [], "msg": "时间窗口内无数据"}

    rows: List[Dict[str, Any]] = []
    by_rule: Dict[str, int] = {}
    by_level: Dict[str, int] = {"1": 0, "2": 0, "3": 0}
    for code, cfg in cfgs.items():
        hits = SYLLABUS_FUNCS[code](data, dates, cfg)
        by_rule[code] = len(hits)
        for h in hits:
            level = int(h.get("warning_level") or cfg["warning_level"])   # 等级由规则函数按严重程度给定
            by_level[str(level)] = by_level.get(str(level), 0) + 1
            rows.append({
                "student_id": h["student_id"], "rule_code": code,
                # rule_name 随记快照：事后改名/停用不回溯历史预警的展示名（models.to_dict 优先读它）
                "rule_name": cfg["rule_name"],
                "warning_type": cfg["warning_type"],
                "warning_level": level,
                "warning_date": h["warning_date"], "metric_value": h.get("metric_value"),
                "detail": h.get("detail", {}), "message": h["message"][:255],
            })

    written = _persist(rows) if persist else 0
    return {
        "persisted": persist,
        "written": written,
        "matched": len(rows),
        "by_rule": by_rule,
        "by_level": by_level,
        "window": [start, end],
        "weeks_compared": [str(w.date()) for w in _complete_weeks(start, end)],
        "rules_enabled": list(cfgs),
        "items": [] if persist else rows[:1000],       # 不落库时把明细带回去，供实时预览
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def refresh(start: str, end: str, rules: Optional[List[str]] = None,
            keep_handled: bool = True) -> Dict[str, Any]:
    """
    "重新计算预警"（POST /api/warning/refresh 的实现）。
    与 scan 的区别：先删掉窗口内本模块产出的预警，再重算 —— 这样**已经不再成立**的
    历史预警会被清掉（例如某学生补录了消费，连续无消费段消失）。
    keep_handled=True 时保留已处置（status<>0）的记录，保住人工审计痕迹。
    """
    ensure_rules()
    codes = list(rules or SYLLABUS_FUNCS)
    # IN :codes 必须声明 expanding，否则 SQLAlchemy 会把元组当成单个绑定值报参数错误
    kept = " AND status = 0" if keep_handled else ""      # 默认只清未处置的，已处理记录要留痕
    sql = text("DELETE FROM warning"
               " WHERE rule_code IN :codes"
               "   AND warning_date BETWEEN :start AND :end" + kept
               ).bindparams(bindparam("codes", expanding=True))
    with db.engine.begin() as conn:
        res = conn.execute(sql, {"codes": tuple(codes), "start": start, "end": end})
        removed = int(res.rowcount or 0)

    result = scan(start, end, codes, persist=True)
    result.update({"removed_stale": removed, "keep_handled": keep_handled})
    return result


def student_warnings(student_id: str, codes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """个体画像页/规则说明用：某学生当前命中的总纲规则（实时计算，不读库、不写库）"""
    from utils import data_range

    s, e = data_range()
    result = scan(s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"), codes, persist=False)
    return [r for r in result["items"] if r["student_id"] == student_id]
