# -*- coding: utf-8 -*-
"""
预警接口
  GET  /api/warning/list        预警列表（状态/级别/类型/学号筛选 + 分页）
  GET  /api/warning/stats       预警统计（大屏环形图 + 近 N 日趋势）
  GET  /api/warning/rules       规则配置列表
  POST /api/warning/scan        执行细粒度扩展规则扫描并落库（幂等，可重复调用）
  POST /api/warning/refresh     重新计算总纲四大规则预警（先清失效项再重算）
  POST /api/warning/<id>/handle 处置预警（标记已处理/已忽略）

两套规则引擎的分工（详见 analysis/warning.py 顶部注释）：
  analysis/warning.py        总纲四大规则（NO_CONSUME / CONSUME_DROP / NO_LIBRARY /
                             NIGHT_WEEK_CONSUME），预警等级按严重程度浮动
  analysis/warning_rules.py  扩展细粒度规则（HIGH_CONSUME / LOW_CONSUME / NIGHT_CONSUME /
                             MEAL_IRREGULAR / OVERSTAY），等级取配置表静态值
  两边 rule_code 不重叠，写同一张 warning 表不会互相覆盖。

说明：warning 表初始为空，需要先调一次 scan + refresh 生成数据；
      真实项目里这一步由 APScheduler 每日凌晨定时跑。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from flask import Blueprint, request
from sqlalchemy import func, or_

from analysis import warning as syllabus
from analysis import warning_rules as extended
from models import Student, Warning, WarningRule, db
from utils import fail, ok, parse_int, resolve_window

bp = Blueprint("warning", __name__, url_prefix="/api/warning")


@bp.get("/list")
def warning_list():
    """
    预警列表页数据源。
    默认排序：级别高的在前、日期新的在前 —— 辅导员打开页面先看到最紧急的。
    """
    page, size = parse_int("page", 1, 1, 10000), parse_int("size", 20, 1, 200)
    q = Warning.query

    status = request.args.get("status")
    if status not in (None, ""):
        q = q.filter(Warning.status == int(status))
    level = request.args.get("level")
    if level:
        q = q.filter(Warning.warning_level >= int(level))
    wtype = request.args.get("type")
    if wtype:
        q = q.filter(Warning.warning_type == wtype)
    rule = request.args.get("rule_code")
    if rule:
        q = q.filter(Warning.rule_code == rule)
    keyword = (request.args.get("keyword") or "").strip()
    if keyword:
        like = f"%{keyword.replace('%', r'\%').replace('_', r'\_')}%"
        q = q.join(Warning.student).filter(or_(Warning.student_id.like(like),
                                               Student.name.like(like)))
    start, end = request.args.get("start"), request.args.get("end")
    if start:
        q = q.filter(Warning.warning_date >= start)
    if end:
        q = q.filter(Warning.warning_date <= end)

    total = q.count()
    rows = (q.order_by(Warning.warning_level.desc(), Warning.warning_date.desc(), Warning.id.desc())
            .offset((page - 1) * size).limit(size).all())
    return ok({"total": total, "page": page, "size": size,
               "items": [w.to_dict() for w in rows]})


@bp.get("/stats")
def warning_stats():
    """按类型/级别/日期三个角度统计，大屏与列表页顶部卡片共用"""
    by_type = db.session.query(Warning.warning_type, func.count(Warning.id)) \
        .group_by(Warning.warning_type).all()
    by_level = db.session.query(Warning.warning_level, func.count(Warning.id)) \
        .group_by(Warning.warning_level).all()
    by_rule = db.session.query(Warning.rule_code, func.count(Warning.id),
                               func.max(Warning.warning_level)) \
        .group_by(Warning.rule_code).order_by(func.count(Warning.id).desc()).all()
    by_date = db.session.query(Warning.warning_date, func.count(Warning.id)) \
        .group_by(Warning.warning_date).order_by(Warning.warning_date).all()
    by_status = db.session.query(Warning.status, func.count(Warning.id)) \
        .group_by(Warning.status).all()
    rule_names = {r.rule_code: r.rule_name for r in WarningRule.query.all()}

    return ok({
        "total": sum(c for _, c in by_type),
        "by_type": [{"type": t, "count": c} for t, c in by_type],
        "by_level": [{"level": int(l), "level_text": {1: "低", 2: "中", 3: "高"}.get(int(l), "中"),
                      "count": c} for l, c in by_level],
        "by_status": [{"status": int(s), "status_text": {0: "未处理", 1: "已处理", 2: "已忽略"}.get(int(s)),
                       "count": c} for s, c in by_status],
        "by_rule": [{"rule_code": r, "rule_name": rule_names.get(r, r), "count": c, "level": int(l)}
                    for r, c, l in by_rule],
        "trend": [{"date": d.strftime("%Y-%m-%d"), "count": c} for d, c in by_date],
    })


@bp.get("/rules")
def warning_rules_list():
    """规则配置：预警列表页的筛选器与规则说明弹窗都读这里"""
    return ok([r.to_dict() for r in WarningRule.query.order_by(WarningRule.id).all()])


@bp.post("/scan")
def warning_scan():
    """
    触发扫描。body/query 可选：
      rule_code  只跑指定规则，如 HIGH_CONSUME
      start/end  扫描窗口，默认取全库区间
    幂等：唯一键 (student_id, rule_code, warning_date) 保证重复调用不产生重复记录。
    本接口只跑扩展细粒度规则；总纲四大规则（含等级浮动）请用 /refresh。
    """
    payload = request.get_json(silent=True) or {}
    start = payload.get("start") or request.args.get("start")
    end = payload.get("end") or request.args.get("end")
    if not start or not end:
        w_start, w_end, _ = resolve_window()
        start, end = start or w_start, end or w_end
    code = payload.get("rule_code") or request.args.get("rule_code")
    rules = [code] if code else None
    result = extended.scan(start, end, rules)
    if rules and not result["rules_enabled"]:
        return fail(f"规则 {code} 不存在或已停用", 400, result)
    return ok(result, f"扫描完成，写入/更新 {result['written']} 条预警")


@bp.post("/refresh")
def warning_refresh():
    """
    重新计算预警 —— 与 /scan 的差别是它带"失效清理"：
    先删掉窗口内本引擎产出且尚未处置的旧预警，再按当前数据重算，
    所以“上周命中、这周已不成立”的预警不会残留在列表里。

    body/query 参数（全部可选）：
      scope         syllabus(默认)-总纲四大规则 / extended-扩展细粒度规则 / all-两者
      rule_code     只重算某一条规则，如 CONSUME_DROP
      start / end   计算窗口，默认全库实际数据区间
      persist       0 = 只实时计算不落库（返回 items 明细，便于核对阈值）
      keep_handled  0 = 连已处置的历史预警也一并重算（默认 1，保留人工处置痕迹）
    """
    payload = request.get_json(silent=True) or {}

    def arg(name, default=None):
        return payload.get(name) if payload.get(name) is not None else request.args.get(name, default)

    start, end = arg("start"), arg("end")
    if not start or not end:
        w_start, w_end, _ = resolve_window()
        start, end = start or w_start, end or w_end
    scope = (arg("scope") or "syllabus").lower()
    if scope not in ("syllabus", "extended", "all"):
        return fail("scope 只能是 syllabus / extended / all")
    code = arg("rule_code")
    persist = str(arg("persist", "1")) not in ("0", "false", "False")
    keep_handled = str(arg("keep_handled", "1")) not in ("0", "false", "False")
    rules = [code] if code else None

    out: Dict[str, Any] = {"window": [start, end], "persisted": persist, "scope": scope}
    merged_rules: Dict[str, int] = {}
    merged_level = {"1": 0, "2": 0, "3": 0}
    written = matched = removed = 0
    weeks: List[str] = []

    if scope in ("syllabus", "all"):
        r = syllabus.refresh(start, end, rules, keep_handled=keep_handled) if persist else \
            syllabus.scan(start, end, rules, persist=False)
        out["syllabus"] = r
        written += int(r.get("written", 0))
        matched += int(r.get("matched", 0))
        removed += int(r.get("removed_stale", 0))
        weeks = list(r.get("weeks_compared") or [])
        merged_rules.update(r.get("by_rule", {}))
        for lv, cnt in (r.get("by_level") or {}).items():
            merged_level[str(lv)] = merged_level.get(str(lv), 0) + int(cnt)

    if scope in ("extended", "all"):
        # 扩展引擎没有"失效清理"需求（它的预警按天累积、幂等更新即可），仍走 scan
        r = extended.scan(start, end, rules if scope == "extended" else None)
        out["extended"] = r
        written += int(r.get("written", 0))
        matched += int(r.get("matched", 0))
        merged_rules.update(r.get("by_rule", {}))

    # matched/removed_stale/weeks_compared 必须上浮到顶层：前端提示“清了几条失效预警”、
    # 冒烟用例断言都只看 data 这一层，埋在 syllabus 子对象里等于没返回
    out.update({"written": written, "matched": matched, "removed_stale": removed,
                "weeks_compared": weeks,
                "by_rule": merged_rules, "by_level": merged_level})
    if not persist:
        out["items"] = (out.get("syllabus") or {}).get("items", [])
    return ok(out, (f"重算完成，写入/更新 {written} 条预警" if persist
                    else f"实时计算完成，命中 {merged_rules and sum(merged_rules.values()) or 0} 条（未落库）"))


@bp.post("/<int:wid>/handle")
def warning_handle(wid: int):
    """处置预警：0-未处理 1-已处理 2-已忽略"""
    payload = request.get_json(silent=True) or {}
    w = db.session.get(Warning, wid)
    if w is None:
        return fail(f"预警记录 {wid} 不存在", 404)
    status = int(payload.get("status", 1))
    if status not in (0, 1, 2):
        return fail("status 只能是 0/1/2")
    w.status = status
    w.handled_by = (payload.get("handled_by") or "system")[:50]
    w.handled_at = datetime.now() if status != 0 else None
    db.session.commit()
    return ok(w.to_dict(), "处置成功")
