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
from typing import Any, Dict, List, Optional

from flask import Blueprint, request
from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import joinedload

from analysis import statistics
from analysis import warning as syllabus
from analysis import warning_catalog as cat
from analysis import warning_rules as extended
from models import Student, Warning, WarningRule, db
from security import audit, current_scope, current_user, require_perm
from utils import fail, ok, parse_date, parse_int, parse_int_strict, resolve_window

bp = Blueprint("warning", __name__, url_prefix="/api/warning")


def _scope_condition():
    """返回限定当前用户数据范围的 Warning 过滤条件；None=全校不过滤；False=空范围无权。"""
    scope = current_scope()
    if scope.all:
        return None
    if scope.is_empty():
        return Warning.id < 0                       # 永假：空范围看不到任何预警
    sub = db.session.query(Student.student_id)
    conds = []
    if scope.student_ids:
        conds.append(Student.student_id.in_(list(scope.student_ids)))
    if scope.colleges:
        conds.append(Student.college.in_(list(scope.colleges)))
    if scope.grades:
        conds.append(Student.grade_year.in_([int(x) for x in scope.grades]))
    if scope.classes:
        conds.append(Student.class_name.in_(list(scope.classes)))
    sub = sub.filter(db.or_(*conds)).subquery()
    return Warning.student_id.in_(db.session.query(sub.c.student_id))


def _check_dates(*names) -> Optional[str]:
    """query 里的日期筛选要么不传、传了就必须能解析，否则给出 400 文案
    （非法日期直接下推 MySQL 只会得到截断警告或 500，前端拿不到可操作的提示）"""
    for n in names:
        raw = request.args.get(n)
        if raw and parse_date(n) is None:
            return f"参数 {n} 日期格式应为 YYYY-MM-DD，收到：{str(raw)[:40]}"
    return None


def _valid_date(v: Any) -> bool:
    """校验 JSON body 里的日期值（query 里的用 _check_dates）：与 utils.parse_date 同格式集"""
    if not v:
        return True
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            datetime.strptime(str(v), fmt)
            return True
        except ValueError:
            continue
    return False


def _filter_conds() -> tuple[list, Optional[str]]:
    """
    列表与统计卡共用的筛选条件（审计问题：顶部统计卡不随日期/级别筛选联动，
    筛到 12 条却显示"总数 482"像统计出错）。返回 (条件列表, 400 文案)；
    关键词用子查询而不是 join，避免与列表页的 joinedload(student) 叠成重复关联。
    """
    conds: list = []
    status, err = parse_int_strict("status", allowed=(0, 1, 2))
    if err:
        return conds, err
    if status is not None:
        conds.append(Warning.status == status)
    level, err = parse_int_strict("level", allowed=(1, 2, 3))
    if err:
        return conds, err
    if level is not None:
        conds.append(Warning.warning_level >= level)      # "最低级别"语义：中及以上
    bad = _check_dates("start", "end")
    if bad:
        return conds, bad
    wtype = (request.args.get("type") or "").strip()[:20]
    if wtype:
        conds.append(Warning.warning_type == wtype)
    rule = (request.args.get("rule_code") or "").strip()[:40]
    if rule:
        conds.append(Warning.rule_code == rule)
    # 阶段 4：工作流/信号类别/核实结论筛选（非法值显式 400，不静默回落）
    wf, err = parse_int_strict("workflow_state", allowed=(0, 1, 2, 3, 4))
    if err:
        return conds, err
    if wf is not None:
        conds.append(Warning.workflow_state == wf)
    vres = (request.args.get("verify_result") or "").strip()[:24]
    if vres:
        if vres not in cat.VERIFY_RESULT_CODES:
            return conds, f"verify_result 只能是 {'/'.join(cat.VERIFY_RESULT_CODES)}"
        conds.append(Warning.verify_result == vres)
    skind = (request.args.get("signal_kind") or "").strip()[:24]
    if skind:
        if skind not in cat.SIGNAL_KIND_CODES:
            return conds, f"signal_kind 只能是 {'/'.join(cat.SIGNAL_KIND_CODES)}"
        conds.append(Warning.signal_kind == skind)
    # 默认排除"数据质量问题"与"重预警"，不让它们占用人工核实队列（需求 6）；
    # 需要看全量时传 include_data_quality=1 / include_duplicate=1
    if str(request.args.get("include_data_quality", "")).lower() not in ("1", "true"):
        conds.append(Warning.signal_kind != "data_quality")
    if str(request.args.get("include_duplicate", "")).lower() not in ("1", "true"):
        conds.append(Warning.is_duplicate == 0)
    keyword = (request.args.get("keyword") or "").strip()[:50]
    if keyword:
        like = f"%{keyword.replace('%', r'\%').replace('_', r'\_')}%"
        conds.append(Warning.student_id.in_(
            db.session.query(Student.student_id).filter(
                or_(Student.student_id.like(like), Student.name.like(like)))))
    start, end = parse_date("start"), parse_date("end")
    if start:
        conds.append(Warning.warning_date >= start)
    if end:
        conds.append(Warning.warning_date <= end)
    scope_cond = _scope_condition()                 # 数据范围强制下推，列表与统计同口径
    if scope_cond is not None:
        conds.append(scope_cond)
    return conds, None


@bp.get("/list")
@require_perm("warning:read")
def warning_list():
    """
    预警列表页数据源。
    默认排序：级别高的在前、日期新的在前 —— 辅导员打开页面先看到最紧急的。
    """
    page, size = parse_int("page", 1, 1, 10000), parse_int("size", 20, 1, 200)
    conds, err = _filter_conds()
    if err:
        return fail(err)
    q = Warning.query.filter(*conds)

    total = q.count()
    # joinedload 预加载学生/规则，消除 to_dict 逐行懒加载的 N+1（size=200 时约 401 查 -> 1 查）；
    # options 只加在取行查询上，不污染上面的 count()
    rows = (q.options(joinedload(Warning.student), joinedload(Warning.rule))
            .order_by(Warning.warning_level.desc(), Warning.warning_date.desc(), Warning.id.desc())
            .offset((page - 1) * size).limit(size).all())
    return ok({"total": total, "page": page, "size": size,
               "items": [w.to_dict() for w in rows]})


@bp.get("/stats")
@require_perm("warning:read")
def warning_stats():
    """按类型/级别/日期三个角度统计，大屏与列表页顶部卡片共用。
    支持与 /list 完全同口径的筛选（前端把同一套 queryParams 传进来，统计卡才不会和表格打架）。"""
    conds, err = _filter_conds()
    if err:
        return fail(err)
    def base():
        return db.session.query(Warning).filter(*conds)
    by_type = base().with_entities(Warning.warning_type, func.count(Warning.id)) \
        .group_by(Warning.warning_type).all()
    by_level = base().with_entities(Warning.warning_level, func.count(Warning.id)) \
        .group_by(Warning.warning_level).all()
    by_rule = base().with_entities(Warning.rule_code, func.count(Warning.id),
                                   func.max(Warning.warning_level)) \
        .group_by(Warning.rule_code).order_by(func.count(Warning.id).desc()).all()
    by_date = base().with_entities(Warning.warning_date, func.count(Warning.id)) \
        .group_by(Warning.warning_date).order_by(Warning.warning_date).all()
    by_status = base().with_entities(Warning.status, func.count(Warning.id)) \
        .group_by(Warning.status).all()
    by_workflow = base().with_entities(Warning.workflow_state, func.count(Warning.id)) \
        .group_by(Warning.workflow_state).all()
    rule_names = {r.rule_code: r.rule_name for r in WarningRule.query.all()}

    return ok({
        "total": sum(c for _, c in by_type),
        "by_type": [{"type": t, "count": c} for t, c in by_type],
        "by_level": [{"level": int(l), "level_text": {1: "低", 2: "中", 3: "高"}.get(int(l), "中"),
                      "count": c} for l, c in by_level],
        "by_status": [{"status": int(s), "status_text": {0: "未处理", 1: "已处理", 2: "已忽略"}.get(int(s)),
                       "count": c} for s, c in by_status],
        # 阶段 4：五态工作流分布（预警只是待核实信号，不是结论）
        "by_workflow": [{"state": int(w), "state_text": cat.WORKFLOW_STATE_TEXT.get(int(w), "待核实"),
                         "count": c} for w, c in by_workflow],
        "by_rule": [{"rule_code": r, "rule_name": rule_names.get(r, r), "count": c, "level": int(l)}
                    for r, c, l in by_rule],
        "trend": [{"date": d.strftime("%Y-%m-%d"), "count": c} for d, c in by_date],
        "disclaimer": cat.DISCLAIMER,
    })


@bp.get("/rules")
@require_perm("warning:read")
def warning_rules_list():
    """规则配置：预警列表页的筛选器与规则说明弹窗都读这里"""
    return ok([r.to_dict() for r in WarningRule.query.order_by(WarningRule.id).all()])


@bp.post("/scan")
@require_perm("warning:run")
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
    if not _valid_date(start) or not _valid_date(end):
        return fail("start/end 日期格式应为 YYYY-MM-DD")
    if not start or not end:
        w_start, w_end, _ = resolve_window()
        start, end = start or w_start, end or w_end
    code = payload.get("rule_code") or request.args.get("rule_code")
    rules = [code] if code else None
    result = extended.scan(start, end, rules)
    if rules and not result["rules_enabled"]:
        return fail(f"规则 {code} 不存在或已停用", 400, result)
    # 预警数变了 → 定向失效概览卡相关缓存（其余统计与 warning 表无关，不必重算）
    statistics.clear_stats_cache(("overview", "summary"))
    return ok(result, f"扫描完成，写入/更新 {result['written']} 条预警")


@bp.post("/refresh")
@require_perm("warning:run")
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
    if not _valid_date(start) or not _valid_date(end):
        return fail("start/end 日期格式应为 YYYY-MM-DD")
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
        # 扩展引擎没有"失效清理"需求（它的预警按天累积、幂等更新即可），仍走 scan。
        # scope=all 时也传递 rules：extended.scan 内部会按 rule_code 过滤，
        # 传入不相关的 code 不会命中任何扩展规则，与 syllabus 的语义保持一致
        r = extended.scan(start, end, rules)
        out["extended"] = r
        written += int(r.get("written", 0))
        matched += int(r.get("matched", 0))
        merged_rules.update(r.get("by_rule", {}))

    # matched/removed_stale/weeks_compared 必须上浮到顶层：前端提示“清了几条失效预警”、
    # 冒烟用例断言都只看 data 这一层，埋在 syllabus 子对象里等于没返回
    out.update({"written": written, "matched": matched, "removed_stale": removed,
                "weeks_compared": weeks,
                "by_rule": merged_rules, "by_level": merged_level})
    if persist:
        statistics.clear_stats_cache(("overview", "summary"))   # 落库改变了预警数，失效概览缓存
    if not persist:
        out["items"] = (out.get("syllabus") or {}).get("items", [])
    return ok(out, (f"重算完成，写入/更新 {written} 条预警" if persist
                    else f"实时计算完成，命中 {merged_rules and sum(merged_rules.values()) or 0} 条（未落库）"))


@bp.post("/<int:wid>/handle")
@require_perm("warning:handle")
def warning_handle(wid: int):
    """处置预警：0-未处理 1-已处理 2-已忽略。处理人取认证身份（不可由前端伪造），
    且只能处置自己数据范围内的预警。"""
    payload = request.get_json(silent=True) or {}
    w = db.session.get(Warning, wid)
    if w is None:
        return fail(f"预警记录 {wid} 不存在", 404)
    # 数据范围：该预警所属学生必须在当前用户授权范围内（否则视同不存在，防越权处置/枚举）
    scope_cond = _scope_condition()
    if scope_cond is not None:
        in_scope = Warning.query.filter(Warning.id == wid, scope_cond).first() is not None
        if not in_scope:
            audit("warning_handle_denied", target=f"warning:{wid}", result="denied")
            return fail(f"预警记录 {wid} 不存在", 404)
    try:
        status = int(payload.get("status", 1))
    except (TypeError, ValueError):
        return fail("status 只能是 0/1/2")
    if status not in (0, 1, 2):
        return fail("status 只能是 0/1/2")
    actor = current_user()
    w.status = status
    w.handled_by = (actor.username if actor else "unknown")[:50]   # 认证身份，忽略客户端传入
    w.handled_at = datetime.now() if status != 0 else None
    db.session.commit()
    audit("warning_handle", target=f"warning:{wid}", detail={"status": status, "student": w.student_id})
    return ok(w.to_dict(), "处置成功")


# =============================================================================
# 阶段 4：人工核实工作流 + 规则级统计
# =============================================================================

# 动作 -> (允许的来源态集合, 目标态)。状态机严格约束，非法跳转直接 400。
# 待核实0 → 已分配1 → 核实中2 → 已核实3 → 已关闭4；申诉/复核从 3/4 回到 0。
_WF_TRANSITIONS = {
    "assign": ({0, 1, 2}, 1),
    "start": ({0, 1, 2}, 2),
    "verify": ({0, 1, 2}, 3),
    "close": ({0, 1, 2, 3}, 4),
    "reopen": ({3, 4}, 0),
    "appeal": ({3, 4}, 0),
}


def _load_warning_in_scope(wid: int):
    """取预警并校验数据范围；返回 (Warning, None) 或 (None, fail 响应)。
    越权/不存在统一 404（不区分，防枚举他人处置记录）。"""
    w = db.session.get(Warning, wid)
    if w is None:
        return None, fail(f"预警记录 {wid} 不存在", 404)
    scope_cond = _scope_condition()
    if scope_cond is not None and \
            Warning.query.filter(Warning.id == wid, scope_cond).first() is None:
        audit("warning_wf_denied", target=f"warning:{wid}", result="denied")
        return None, fail(f"预警记录 {wid} 不存在", 404)
    return w, None


@bp.post("/<int:wid>/workflow")
@require_perm("warning:handle")
def warning_workflow(wid: int):
    """
    推进预警的人工核实工作流（需求 7/8/9）：
      assign  分配处理人        body: {assigned_to}
      start   开始核实
      verify  给出核实结论      body: {verify_result, verify_note}
      close   关闭
      reopen  重新打开（复核）   body: {verify_note}
      appeal  申诉纠正          body: {verify_note}   （必填理由，回到待核实重新处理）
    处理人/核实人一律取认证身份，不接受前端伪造；只能操作授权范围内的预警。
    旧 status 同步回写以兼容历史统计，但工作流状态以 workflow_state 为准。
    """
    w, err = _load_warning_in_scope(wid)
    if err is not None:
        return err
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    if action not in _WF_TRANSITIONS:
        return fail(f"action 只能是 {'/'.join(_WF_TRANSITIONS)}，收到：{action[:24]}")
    allowed_from, target = _WF_TRANSITIONS[action]
    if int(w.workflow_state or 0) not in allowed_from:
        return fail(f"当前状态「{cat.WORKFLOW_STATE_TEXT.get(int(w.workflow_state or 0))}」"
                    f"不能执行「{action}」", 409)

    actor = current_user()
    who = (actor.username if actor else "unknown")[:50]
    now = datetime.now()
    note = str(payload.get("verify_note") or "").strip()[:500]

    if action == "assign":
        assignee = str(payload.get("assigned_to") or "").strip()[:50]
        if not assignee:
            return fail("assign 需要提供 assigned_to")
        w.assigned_to, w.assigned_at = assignee, now
    elif action == "verify":
        vres = str(payload.get("verify_result") or "").strip().lower()
        if vres not in cat.VERIFY_RESULT_CODES:
            return fail(f"verify_result 只能是 {'/'.join(cat.VERIFY_RESULT_CODES)}")
        if not note:
            return fail("verify 需要提供 verify_note（核实结论与依据说明）")
        w.verify_result, w.verify_note, w.verified_by, w.verified_at = vres, note, who, now
        # 兼容旧列：让既有"处置"展示与统计仍能读到处置人与时间
        w.handled_by, w.handled_at = who, now
        w.status = 2 if vres in ("false_positive", "data_issue") else 1
        # 需求 2："经人工确认的实际支持需求" 才把信号升级为 confirmed_support（唯一可正向日标的类别）
        if vres == "need_support":
            w.signal_kind = "confirmed_support"
    elif action in ("reopen", "appeal"):
        if action == "appeal":
            if not note:
                return fail("appeal 需要提供 verify_note（申诉/纠正理由）")
            w.verify_note = (f"[申诉] {note}")[:500]
        w.verify_result, w.verified_by, w.verified_at = None, None, None
        w.status = 0
    elif action == "close":
        w.handled_by, w.handled_at = w.handled_by or who, w.handled_at or now
        w.status = w.status if w.status != 0 else 1

    w.workflow_state = target
    db.session.commit()
    audit("warning_workflow", target=f"warning:{wid}",
          detail={"action": action, "to": target, "student": w.student_id})
    return ok(w.to_dict(), f"操作成功：{cat.WORKFLOW_STATE_TEXT.get(target)}")


@bp.get("/rule-stats")
@require_perm("warning:read")
def warning_rule_stats():
    """
    规则级统计（需求 10）：每条规则的触发数量、核实数量、误报数量、
    平均处理时长（分钟）、重复预警数量、数据缺失比例。
    与列表不同：本接口统看全量（含 data_quality / 重复项），受当前用户数据范围约束。
    需求 11：在获得可靠人工核实标签前不报任何"预测准确率"，只报"已核实覆盖率"这一
    中性度量，并附全局免责。
    """
    conds: list = []
    bad = _check_dates("start", "end")
    if bad:
        return fail(bad)
    start, end = parse_date("start"), parse_date("end")
    if start:
        conds.append(Warning.warning_date >= start)
    if end:
        conds.append(Warning.warning_date <= end)
    wtype = (request.args.get("type") or "").strip()[:20]
    if wtype:
        conds.append(Warning.warning_type == wtype)
    scope_cond = _scope_condition()
    if scope_cond is not None:
        conds.append(scope_cond)

    minutes = func.timestampdiff(text("MINUTE"), Warning.created_at, Warning.verified_at)
    rows = (db.session.query(
                Warning.rule_code,
                func.count(Warning.id),
                func.sum(case((Warning.workflow_state >= 3, 1), else_=0)),
                func.sum(case((Warning.verify_result == "false_positive", 1), else_=0)),
                func.sum(case((Warning.verify_result == "need_support", 1), else_=0)),
                func.sum(case((Warning.is_duplicate == 1, 1), else_=0)),
                func.sum(case((Warning.signal_kind == "data_quality", 1), else_=0)),
                func.avg(case((Warning.verified_at.isnot(None), minutes), else_=None)),
            ).filter(*conds)
            .group_by(Warning.rule_code)
            .order_by(func.count(Warning.id).desc()).all())

    rule_names = {r.rule_code: r.rule_name for r in WarningRule.query.all()}
    items = []
    tot = verified = 0
    for code, cnt, ver, fp, ns, dup, dq, avg_min in rows:
        cnt = int(cnt or 0)
        tot += cnt
        verified += int(ver or 0)
        items.append({
            "rule_code": code,
            "rule_name": rule_names.get(code, code),
            "triggered": cnt,
            "verified": int(ver or 0),
            "false_positive": int(fp or 0),
            "need_support": int(ns or 0),
            "duplicates": int(dup or 0),
            "data_quality": int(dq or 0),
            "data_gap_ratio": round(int(dq or 0) / cnt * 100, 2) if cnt else 0.0,
            "dup_ratio": round(int(dup or 0) / cnt * 100, 2) if cnt else 0.0,
            "avg_handle_minutes": round(float(avg_min), 1) if avg_min is not None else None,
        })
    return ok({
        "items": items,
        "summary": {
            "triggered": tot,
            "verified": verified,
            # 覆盖率 = 已核实数 / 总触发数；这是中性度量，不等于、也不宣称预测准确率
            "verified_coverage": round(verified / tot * 100, 2) if tot else 0.0,
        },
        "accuracy_note": "尚无足够可靠人工核实标签，系统不宣称任何风险预测准确率；"
                         "verified_coverage 仅为核实进度指标，非模型精度。",
        "disclaimer": cat.DISCLAIMER,
    })
