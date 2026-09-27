# -*- coding: utf-8 -*-
"""
SQLAlchemy 模型 —— 与 database/schema.sql 严格一一对应

要点：
1. consumption.meal_period、library_record.stay_minutes 是 MySQL STORED 生成列，
   必须用 FetchedValue() 声明，ORM 才会"只读不写"（INSERT/UPDATE 都不带这两列）。
2. 主键沿用业务键 student_id（VARCHAR），与数据生成器、pandas 结果、前端图表共用同一 key。
3. warning.rule_code -> warning_rule.rule_code 是逻辑外键（不建物理约束），
   因为规则停用/改名时历史预警必须保持原样。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import FetchedValue

db = SQLAlchemy()

# 消费场景编码 -> 名称（与 schema 中 merchant_type 注释一致，供前端展示复用）
MERCHANT_TYPES = {1: "食堂", 2: "超市", 3: "浴室", 4: "机房", 5: "其他"}
WARNING_STATUS = {0: "未处理", 1: "已处理", 2: "已忽略"}
WARNING_LEVELS = {1: "低", 2: "中", 3: "高"}
# 阶段 4：人工核实工作流五态（预警只是待核实信号，不是结论）
WORKFLOW_STATES = {0: "待核实", 1: "已分配", 2: "核实中", 3: "已核实", 4: "已关闭"}
# 核实结论：确认支持需求 / 误报 / 数据问题 / 其它（未核实时为空）
VERIFY_RESULTS = {"need_support": "确认需支持", "false_positive": "误报",
                  "data_issue": "数据问题", "other": "其它"}
# 信号五分类（阶段 4 需求 2）：把预警拆成不同性质，避免一律当作"异常"
SIGNAL_KINDS = {"objective_record": "客观行为记录", "personal_change": "相对个人历史变化",
                "data_quality": "数据质量问题", "need_verification": "待人工核实信号",
                "confirmed_support": "经核实的支持需求"}


class Student(db.Model):
    """学生基础信息（维度表）"""

    __tablename__ = "student"
    __table_args__ = {"comment": "学生基础信息表"}

    student_id = db.Column("student_id", db.String(20), primary_key=True, comment="学号，业务主键")
    name = db.Column(db.String(50), nullable=False, comment="姓名")
    gender = db.Column(db.SmallInteger, nullable=False, default=0, comment="0-未知 1-男 2-女")
    birth_year = db.Column(db.SmallInteger, comment="出生年份")
    college = db.Column(db.String(50), nullable=False, comment="学院")
    major = db.Column(db.String(50), nullable=False, comment="专业")
    class_name = db.Column(db.String(50), comment="班级")
    grade_year = db.Column(db.SmallInteger, nullable=False, comment="入学年份")
    dorm_building = db.Column(db.String(50), comment="宿舍楼")
    card_no = db.Column(db.String(32), comment="一卡通号")
    enroll_status = db.Column(db.SmallInteger, nullable=False, default=1, comment="0-离校 1-在校 2-休学")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # 一对多关系：便于 profile 接口直接 student.consumptions 取流水（注意大数据量下慎用）
    consumptions = db.relationship("Consumption", backref="student", lazy="noload",
                                   cascade="all, delete-orphan")
    library_records = db.relationship("LibraryRecord", backref="student", lazy="noload",
                                      cascade="all, delete-orphan")
    warnings = db.relationship("Warning", backref="student", lazy="select",
                               cascade="all, delete-orphan")

    @property
    def age(self) -> Optional[int]:
        return (datetime.now().year - self.birth_year) if self.birth_year else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "gender": self.gender,
            "gender_text": {1: "男", 2: "女"}.get(self.gender, "未知"),
            "age": self.age,
            "college": self.college,
            "major": self.major,
            "class_name": self.class_name,
            "grade_year": self.grade_year,
            "dorm_building": self.dorm_building,
        }

    def __repr__(self) -> str:
        return f"<Student {self.student_id} {self.name}>"


class Consumption(db.Model):
    """消费流水（事实表，数据量最大）"""

    __tablename__ = "consumption"
    __table_args__ = {"comment": "消费记录表"}

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(20), db.ForeignKey("student.student_id", name="fk_cons_student"),
                           nullable=False, index=True, comment="学号")
    merchant_type = db.Column(db.SmallInteger, nullable=False, default=1, comment="1-食堂 2-超市 3-浴室 4-机房 5-其他")
    merchant_name = db.Column(db.String(80), nullable=False, comment="商户/窗口")
    amount = db.Column(db.Numeric(10, 2), nullable=False, comment="金额（元）")
    balance = db.Column(db.Numeric(10, 2), comment="消费后余额")
    terminal_id = db.Column(db.String(32), comment="机具编号")
    consumed_at = db.Column(db.DateTime, nullable=False, index=True, comment="消费时间")
    # ---- STORED 生成列：数据库自动计算，只读 ----
    meal_period = db.Column(db.String(10), FetchedValue(), comment="餐段（生成列）")
    is_valid = db.Column(db.SmallInteger, nullable=False, default=1, comment="0-脏数据 1-有效")
    batch_no = db.Column(db.String(40), comment="导入批次号")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "merchant_type": self.merchant_type,
            "merchant_type_text": MERCHANT_TYPES.get(self.merchant_type, "其他"),
            "merchant_name": self.merchant_name,
            "amount": float(self.amount or 0),
            "balance": float(self.balance) if self.balance is not None else None,
            "consumed_at": self.consumed_at.strftime("%Y-%m-%d %H:%M:%S") if self.consumed_at else None,
            "meal_period": self.meal_period,
        }


class LibraryRecord(db.Model):
    """图书馆进出记录（事实表）"""

    __tablename__ = "library_record"
    __table_args__ = {"comment": "图书馆进出记录表"}

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(20), db.ForeignKey("student.student_id", name="fk_lib_student"),
                           nullable=False, index=True, comment="学号")
    venue = db.Column(db.String(50), nullable=False, default="中心图书馆", comment="馆舍")
    floor_no = db.Column(db.SmallInteger, comment="楼层")
    area_name = db.Column(db.String(50), comment="区域")
    seat_no = db.Column(db.String(20), comment="座位号")
    gate_in_time = db.Column(db.DateTime, nullable=False, index=True, comment="入馆时间")
    gate_out_time = db.Column(db.DateTime, comment="离馆时间，NULL=仍在馆")
    # ---- STORED 生成列：停留时长（分钟）由数据库算 ----
    stay_minutes = db.Column(db.Integer, FetchedValue(), comment="停留时长（分钟，生成列）")
    in_meal_flag = db.Column(db.SmallInteger, nullable=False, default=0, comment="是否跨餐占座")
    is_valid = db.Column(db.SmallInteger, nullable=False, default=1, comment="0-脏数据 1-有效")
    batch_no = db.Column(db.String(40), comment="导入批次号")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        fmt = "%Y-%m-%d %H:%M:%S"
        return {
            "id": self.id,
            "student_id": self.student_id,
            "venue": self.venue,
            "floor_no": self.floor_no,
            "area_name": self.area_name,
            "seat_no": self.seat_no,
            "gate_in_time": self.gate_in_time.strftime(fmt) if self.gate_in_time else None,
            "gate_out_time": self.gate_out_time.strftime(fmt) if self.gate_out_time else None,
            "stay_minutes": self.stay_minutes,
            "in_meal_flag": self.in_meal_flag,
        }


class WarningRule(db.Model):
    """预警规则阈值配置（阈值外置，前端可改，不改代码）"""

    __tablename__ = "warning_rule"
    __table_args__ = {"comment": "预警规则阈值配置表"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rule_code = db.Column(db.String(40), unique=True, nullable=False, comment="规则编码")
    rule_name = db.Column(db.String(80), nullable=False, comment="规则名称")
    warning_type = db.Column(db.String(30), nullable=False, comment="consume/study/health")
    threshold_value = db.Column(db.Numeric(12, 2), comment="数值阈值")
    threshold_json = db.Column(db.JSON, comment="复杂规则参数")
    warning_level = db.Column(db.SmallInteger, nullable=False, default=2, comment="1-低 2-中 3-高")
    enabled = db.Column(db.SmallInteger, nullable=False, default=1, comment="0-停用 1-启用")
    description = db.Column(db.String(255), comment="规则说明")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "warning_type": self.warning_type,
            "threshold_value": float(self.threshold_value) if self.threshold_value is not None else None,
            "threshold_json": self.threshold_json,
            "warning_level": self.warning_level,
            "warning_level_text": WARNING_LEVELS.get(self.warning_level, "中"),
            "enabled": self.enabled,
            "description": self.description,
        }


class Warning(db.Model):
    """异常行为预警记录（规则引擎输出）"""

    __tablename__ = "warning"
    __table_args__ = {"comment": "异常行为预警记录表"}

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(20), db.ForeignKey("student.student_id", name="fk_warn_student"),
                           nullable=False, index=True, comment="学号")
    rule_code = db.Column(db.String(40), nullable=False, comment="触发的规则编码（逻辑外键）")
    # 规则名快照：扫描写入时随带当时的 rule_name，事后改名/停用不回溯历史预警；
    # 旧数据未回填时 to_dict 仍回退到规则表回查（与历史行为一致）
    rule_name = db.Column(db.String(80), comment="规则名称快照（触发时）")
    warning_type = db.Column(db.String(30), nullable=False, comment="consume/study/health（冗余，免回表）")
    warning_level = db.Column(db.SmallInteger, nullable=False, default=2, comment="1-低 2-中 3-高")
    warning_date = db.Column(db.Date, nullable=False, comment="业务日期")
    metric_value = db.Column(db.Numeric(12, 2), comment="触发时指标值")
    detail_json = db.Column(db.JSON, comment="证据快照")
    message = db.Column(db.String(255), nullable=False, comment="预警文案")
    status = db.Column(db.SmallInteger, nullable=False, default=0, comment="0-未处理 1-已处理 2-已忽略")
    handled_by = db.Column(db.String(50), comment="处理人")
    handled_at = db.Column(db.DateTime, comment="处理时间")

    # ---- 阶段 4：规则口径快照（触发时冻结，事后改规则不回溯历史）----
    rule_version = db.Column(db.String(32), comment="规则版本快照（触发时）")
    signal_kind = db.Column(db.String(24), default="need_verification",
                            comment="信号类别，见 SIGNAL_KINDS")
    metric_def = db.Column(db.String(255), comment="指标定义快照（口径文字）")
    window_start = db.Column(db.Date, comment="计算时间窗起")
    window_end = db.Column(db.Date, comment="计算时间窗止")
    valid_data_days = db.Column(db.Integer, comment="窗口内该生有效数据天数")
    min_data_days = db.Column(db.Integer, comment="规则要求的最小有效数据量")
    baseline_ref = db.Column(db.String(255), comment="个人历史基线描述")
    data_gap_note = db.Column(db.String(255), comment="数据缺失/假期/导入延迟说明")

    # ---- 阶段 4：人工核实工作流（与旧 status 并存，推进时同步回写）----
    workflow_state = db.Column(db.SmallInteger, nullable=False, default=0,
                               comment="0待核实 1已分配 2核实中 3已核实 4已关闭")
    assigned_to = db.Column(db.String(50), comment="分配处理人")
    assigned_at = db.Column(db.DateTime, comment="分配时间")
    verify_result = db.Column(db.String(24), comment="核实结论 need_support/false_positive/data_issue/other")
    verify_note = db.Column(db.String(500), comment="核实/误报/申诉原因记录")
    verified_by = db.Column(db.String(50), comment="核实人")
    verified_at = db.Column(db.DateTime, comment="核实时间")

    # ---- 阶段 4：去重（同生同规则重叠窗口只留一条待办）----
    dedup_key = db.Column(db.String(64), index=True, comment="去重键 sha256(学生|规则|窗口)")
    is_duplicate = db.Column(db.SmallInteger, nullable=False, default=0,
                             comment="1=与既有待办重叠的重复预警")

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    # 逻辑外键：不建物理约束，规则被停用也能显示历史预警名称。
    # 必须显式 uselist=False：没有 ForeignKey 时 SQLAlchemy 无法推断方向，
    # 默认当 one-to-many 返回 list，取 rule_name 就会报 InstrumentedList 无此属性。
    rule = db.relationship("WarningRule",
                           primaryjoin="foreign(Warning.rule_code) == WarningRule.rule_code",
                           uselist=False, viewonly=True, lazy="select")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "student_name": self.student.name if self.student else None,
            "college": self.student.college if self.student else None,
            "class_name": self.student.class_name if self.student else None,
            "rule_code": self.rule_code,
            # 优先用触发时的快照名；没有快照（历史存量行）才回退到当前规则表，再退到编码
            "rule_name": self.rule_name or (self.rule.rule_name if self.rule else self.rule_code),
            "warning_type": self.warning_type,
            "warning_level": self.warning_level,
            "warning_level_text": WARNING_LEVELS.get(self.warning_level, "中"),
            "warning_date": self.warning_date.strftime("%Y-%m-%d") if self.warning_date else None,
            # 预警记录的"触发时间"= 规则引擎写入这条记录的时刻（warning_date 是业务日期，两者不同）
            "triggered_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "metric_value": float(self.metric_value) if self.metric_value is not None else None,
            "detail": self.detail_json,
            "message": self.message,
            "status": self.status,
            "status_text": WARNING_STATUS.get(self.status, "未处理"),
            "handled_by": self.handled_by,
            "handled_at": self.handled_at.strftime("%Y-%m-%d %H:%M") if self.handled_at else None,
            # ---- 阶段 4：规则口径快照 ----
            "rule_version": self.rule_version,
            "signal_kind": self.signal_kind,
            "signal_kind_text": SIGNAL_KINDS.get(self.signal_kind, self.signal_kind),
            "metric_def": self.metric_def,
            "window_start": self.window_start.strftime("%Y-%m-%d") if self.window_start else None,
            "window_end": self.window_end.strftime("%Y-%m-%d") if self.window_end else None,
            "valid_data_days": self.valid_data_days,
            "min_data_days": self.min_data_days,
            "baseline_ref": self.baseline_ref,
            "data_gap_note": self.data_gap_note,
            # ---- 阶段 4：人工核实工作流 ----
            "workflow_state": self.workflow_state,
            "workflow_state_text": WORKFLOW_STATES.get(self.workflow_state, "待核实"),
            "assigned_to": self.assigned_to,
            "assigned_at": self.assigned_at.strftime("%Y-%m-%d %H:%M") if self.assigned_at else None,
            "verify_result": self.verify_result,
            "verify_result_text": VERIFY_RESULTS.get(self.verify_result),
            "verify_note": self.verify_note,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at.strftime("%Y-%m-%d %H:%M") if self.verified_at else None,
            "dedup_key": self.dedup_key,
            "is_duplicate": int(self.is_duplicate or 0),
        }


# =============================================================================
# 阶段 1：生产级认证与权限（RBAC / 数据范围 / 会话 / 审计）
# 建表由 backend/migrations 的 Alembic 迁移 0001 管理（不再用 db.create_all）；
# 现有 5 张业务表与历史数据不受影响。命名/存储哈希见 security.py。
# =============================================================================

class SystemUser(db.Model):
    """系统用户（登录主体）。口令只存 pbkdf2 哈希，永不存明文。"""

    __tablename__ = "system_user"
    __table_args__ = {"comment": "系统用户表（登录主体，口令仅存哈希）"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False, comment="登录名")
    password_hash = db.Column(db.String(255), nullable=False, comment="pbkdf2:sha256 哈希")
    display_name = db.Column(db.String(80), comment="显示名（审计回显用）")
    status = db.Column(db.SmallInteger, nullable=False, default=1, comment="0-禁用 1-启用")
    # 登录失败限流：计数与锁定截止时间落库，多进程/重启后依然生效（内存桶只做补充）
    failed_attempts = db.Column(db.Integer, nullable=False, default=0, comment="连续登录失败次数")
    locked_until = db.Column(db.DateTime, comment="锁定截止时间，未到期拒绝登录")
    must_change_password = db.Column(db.SmallInteger, nullable=False, default=0,
                                     comment="1=下次登录强制改密（管理员重置后置 1）")
    last_login_at = db.Column(db.DateTime, comment="最近一次成功登录")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    roles = db.relationship("UserRole", backref="user", lazy="select", cascade="all, delete-orphan")
    scopes = db.relationship("UserStudentScope", backref="user", lazy="select",
                             cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "username": self.username, "display_name": self.display_name,
            "status": self.status, "roles": [r.role_code for r in self.roles],
            "locked": bool(self.locked_until and self.locked_until > datetime.now()),
            "must_change_password": bool(self.must_change_password),
            "last_login_at": self.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_login_at else None,
        }


class Role(db.Model):
    """角色字典（迁移内种子：system_admin/counselor/analyst/auditor）"""

    __tablename__ = "role"
    __table_args__ = {"comment": "角色表"}

    code = db.Column(db.String(32), primary_key=True, comment="角色码")
    name = db.Column(db.String(64), nullable=False, comment="中文名")
    description = db.Column(db.String(255), comment="职责说明")

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "name": self.name, "description": self.description}


class Permission(db.Model):
    """权限字典（接口层用 code 声明，见 security.PERMISSIONS）"""

    __tablename__ = "permission"
    __table_args__ = {"comment": "权限表"}

    code = db.Column(db.String(64), primary_key=True, comment="权限码，如 student:detail")
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(255))


class RolePermission(db.Model):
    """角色-权限映射（授权变更属敏感操作，调用方必须写审计）"""

    __tablename__ = "role_permission"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role_code = db.Column(db.String(32), db.ForeignKey("role.code", name="fk_rp_role"), nullable=False)
    permission_code = db.Column(db.String(64), db.ForeignKey("permission.code", name="fk_rp_perm"),
                                nullable=False)
    __table_args__ = (
        db.UniqueConstraint("role_code", "permission_code", name="uk_rp"),
        {"comment": "角色-权限映射表"},
    )


class UserRole(db.Model):
    """用户-角色分配（一人可多角色，权限取并集）"""

    __tablename__ = "user_role"
    __table_args__ = (
        db.UniqueConstraint("user_id", "role_code", name="uk_user_role"),
        db.ForeignKeyConstraint(["user_id"], ["system_user.id"], name="fk_ur_user"),
        db.ForeignKeyConstraint(["role_code"], ["role.code"], name="fk_ur_role"),
        {"comment": "用户-角色表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    role_code = db.Column(db.String(32), nullable=False)

    role = db.relationship("Role", lazy="joined")


class UserStudentScope(db.Model):
    """
    用户数据范围（行级授权的物理存储）：
      scope_type = college | grade | class | student_id | *
      - '*' 为显式全量授权（仅给确需全校明细的角色，宁缺勿滥）
      - 无任何范围行的 counselor 默认看不到任何学生（最小权限原则）
      - 授权变更必须写审计（security.audit_write）
    """

    __tablename__ = "user_student_scope"
    __table_args__ = (
        db.Index("uk_scope", "user_id", "scope_type", "scope_value", unique=True),
        db.ForeignKeyConstraint(["user_id"], ["system_user.id"], name="fk_scope_user"),
        {"comment": "用户-学生数据范围表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)     # 联合索引已含 user_id 前缀，不重复建索引
    scope_type = db.Column(db.String(16), nullable=False, comment="college|grade|class|student_id|*")
    scope_value = db.Column(db.String(64), nullable=False, comment="范围值；type='*' 时固定写 '*'")
    granted_by = db.Column(db.String(64), comment="授权人 username（审计冗余）")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)


class LoginSession(db.Model):
    """
    登录会话（httpOnly Cookie 的服务端状态）：
      - 主键直接就是会话令牌的 sha256 哈希：Cookie 泄了也换不回令牌本身，
        数据库被盗也无法重放（还需 Cookie 明文匹配，而异步拿不到 httpOnly）。
      - 吊销：revoke_session/禁用账号/改密均即时生效（每次请求都查本表）。
    """

    __tablename__ = "login_session"
    __table_args__ = {"comment": "登录会话表（支持吊销/过期/主动退出）"}

    token_hash = db.Column(db.String(64), primary_key=True, comment="会话令牌的 sha256 hex")
    user_id = db.Column(db.Integer, db.ForeignKey("system_user.id", name="fk_sess_user"),
                        nullable=False, index=True)
    csrf_token = db.Column(db.String(64), nullable=False, comment="双提交 CSRF 令牌（可读 Cookie 镜像）")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    revoked_at = db.Column(db.DateTime, comment="非空=已吊销（退出/改密/禁用/管理员踢出）")
    ip = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))

    user = db.relationship("SystemUser", lazy="joined")


class AuditLog(db.Model):
    """
    操作审计（只追写不修改；保留期满后由 CLI 清理/匿名化，见 cli_users.py purge-audit）。
    绝不写入：明文口令、完整会话令牌、学生行为明细本身（只记动作与参数摘要）。
    """

    __tablename__ = "audit_log"
    __table_args__ = {
        "comment": "操作审计日志表（登录/授权变更/数据访问/预警处置等）",
    }

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)
    user_id = db.Column(db.Integer, comment="操作人（匿名事件为空，不建外键：用户删除后审计仍要留存）")
    username = db.Column(db.String(64), comment="操作人快照")
    action = db.Column(db.String(64), nullable=False, index=True,
                       comment="login_ok/login_fail/logout/student_view/warning_handle/... ")
    target = db.Column(db.String(128), comment="对象标识（如学号/预警id，存脱敏值）")
    detail = db.Column(db.JSON, comment="参数摘要（已脱敏，不含敏感值本体）")
    ip = db.Column(db.String(64))
    request_id = db.Column(db.String(36), comment="请求追踪 ID，与服务日志关联")
    result = db.Column(db.String(16), default="ok", comment="ok/denied/error")


# =============================================================================
# 阶段 2：每日聚合预计算 / 数据导入批次 / 异步分析作业
# =============================================================================

class StudentDailyStats(db.Model):
    """
    学生每日行为聚合预计算表（阶段 2）。

    目的：将消费/图书馆的 GROUP BY student_id, DATE(...) 结果预先物化，
    避免聚类特征构建(build_features)对原始事实表进行全表扫描。
    刷新路径：
      - 启动时异步提交 daily_stats_refresh 作业
      - 数据导入完成后自动刷新对应日期
      - POST /api/stats/daily/refresh 手动触发

    注：此表是派生结果，不包含原始明细。如原始数据被修改/删除，
    必须重新刷新相关日期的统计。
    """

    __tablename__ = "student_daily_stats"
    __table_args__ = (
        db.UniqueConstraint("student_id", "stat_date", name="uq_sds_student_date"),
        db.Index("idx_sds_date", "stat_date"),
        {"comment": "学生每日行为聚合预计算表（阶段 2：加速窗口统计和 K-Means 特征构建）"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(20), nullable=False, comment="学号")
    stat_date = db.Column(db.Date, nullable=False, comment="统计日期")
    # ---- 消费聚合（来自 consumption WHERE is_valid=1）----
    cons_count = db.Column(db.SmallInteger, nullable=False, default=0, comment="当日消费笔数")
    cons_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0, comment="当日消费总额（元）")
    cons_night = db.Column(db.SmallInteger, nullable=False, default=0, comment="深夜(23:00-05:00)笔数")
    cons_breakfast = db.Column(db.SmallInteger, nullable=False, default=0, comment="有早餐段记录: 1/0")
    cons_lunch = db.Column(db.SmallInteger, nullable=False, default=0, comment="有午餐段记录: 1/0")
    cons_dinner = db.Column(db.SmallInteger, nullable=False, default=0, comment="有晚餐段记录: 1/0")
    cons_weekend = db.Column(db.SmallInteger, nullable=False, default=0, comment="当日是否周末: 1/0")
    # ---- 图书馆聚合（来自 library_record WHERE is_valid=1）----
    lib_visits = db.Column(db.SmallInteger, nullable=False, default=0, comment="当日入馆次数")
    lib_minutes = db.Column(db.Integer, nullable=False, default=0, comment="当日在馆总分钟")
    lib_evening = db.Column(db.SmallInteger, nullable=False, default=0, comment="18时后进馆次数")
    # ---- 元数据 ----
    computed_at = db.Column(db.DateTime, nullable=False, default=datetime.now, comment="最后刷新时间")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "stat_date": str(self.stat_date),
            "cons_count": self.cons_count, "cons_amount": float(self.cons_amount or 0),
            "cons_night": self.cons_night,
            "cons_breakfast": self.cons_breakfast, "cons_lunch": self.cons_lunch,
            "cons_dinner": self.cons_dinner, "cons_weekend": self.cons_weekend,
            "lib_visits": self.lib_visits, "lib_minutes": self.lib_minutes,
            "lib_evening": self.lib_evening,
            "computed_at": self.computed_at.strftime("%Y-%m-%d %H:%M:%S") if self.computed_at else None,
        }


class ImportJob(db.Model):
    """
    数据导入批次记录（阶段 2）。

    幂等：_idempotency_key = SHA256(job_type + 文件字节)，同文件重复上传
          不产生重复导入，直接返回原批次。
    回滚：每批导入写入 batch_no = str(import_job.id)，
          可按批次号删除已导入记录（不删除原始学生基础信息）。
    审计：导入成功/失败均写 AuditLog（import_batch action）。
    """

    __tablename__ = "import_job"
    __table_args__ = {"comment": "数据导入批次记录（幂等键防重复导入）"}

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(32), nullable=False,
                         comment="csv_consumption / csv_library")
    status = db.Column(db.String(16), nullable=False, default="pending",
                       comment="pending/running/success/failed/cancelled")
    file_name = db.Column(db.String(255), comment="上传文件名（用于审计展示）")
    idempotency_key = db.Column(db.String(64), unique=True, nullable=False,
                                comment="SHA256(job_type+file_bytes)，重复提交直接返回原批次")
    scope_note = db.Column(db.String(255), comment="导入批次说明（数据来源/适用范围/文件说明）")
    total_rows = db.Column(db.Integer, default=0, comment="CSV 总数据行（不含表头）")
    imported_rows = db.Column(db.Integer, default=0, comment="成功写入行数")
    skipped_rows = db.Column(db.Integer, default=0, comment="校验失败/重复跳过行数")
    error_rows = db.Column(db.Integer, default=0, comment="错误行数（含同 skipped，语义区分）")
    error_detail = db.Column(db.JSON, comment="前 100 条错误明细 [{row:n, reason:...}]")
    batch_no = db.Column(db.String(40), comment="写入事实表的批次号（=str(import_job.id)，可回滚）")
    created_by = db.Column(db.Integer, comment="提交人 system_user.id（无外键：用户删除后审计仍保留）")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    started_at = db.Column(db.DateTime, comment="开始处理时间")
    finished_at = db.Column(db.DateTime, comment="完成时间")

    def to_dict(self) -> Dict[str, Any]:
        fmt = "%Y-%m-%d %H:%M:%S"
        return {
            "id": self.id, "job_type": self.job_type, "status": self.status,
            "file_name": self.file_name, "scope_note": self.scope_note,
            "total_rows": self.total_rows, "imported_rows": self.imported_rows,
            "skipped_rows": self.skipped_rows, "error_rows": self.error_rows,
            "error_detail": (self.error_detail or [])[:20],  # 响应中只返回前 20 条
            "batch_no": self.batch_no,
            "created_by": self.created_by,
            "created_at": self.created_at.strftime(fmt) if self.created_at else None,
            "started_at": self.started_at.strftime(fmt) if self.started_at else None,
            "finished_at": self.finished_at.strftime(fmt) if self.finished_at else None,
        }


class AnalysisJob(db.Model):
    """
    异步分析作业记录（阶段 2）。

    生命周期：pending → running → success | failed | cancelled
    超时：后台 worker 在 timeout_seconds 内未完成则标记为 failed（错误信息含超时提示）。
    取消：pending 作业直接标记 cancelled；running 作业设置取消标志，作业内部循环检查。
    恢复：进程重启时 worker 自动将遗留 running 作业标记为 failed（崩溃恢复），
          pending 作业重新入队。
    """

    __tablename__ = "analysis_job"
    __table_args__ = {"comment": "异步分析作业（聚类/日统计刷新等）"}

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(32), nullable=False,
                         comment="clustering / elbow_curve / daily_stats_refresh")
    status = db.Column(db.String(16), nullable=False, default="pending",
                       comment="pending/running/success/failed/cancelled")
    params = db.Column(db.JSON, comment="作业参数 {k, feature_set, start, end} 等")
    scope_key = db.Column(db.String(512), comment="提交时用户数据范围 Scope.key()（适用性声明）")
    result_summary = db.Column(db.JSON, comment="作业完成后摘要（不保存逐学生明细）")
    error_msg = db.Column(db.String(512), comment="失败原因")
    created_by = db.Column(db.Integer, comment="提交人 system_user.id")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    started_at = db.Column(db.DateTime, comment="开始运行时间")
    finished_at = db.Column(db.DateTime, comment="完成/失败/取消时间")
    timeout_seconds = db.Column(db.Integer, nullable=False, default=300, comment="超时限制（秒）")

    def to_dict(self) -> Dict[str, Any]:
        fmt = "%Y-%m-%d %H:%M:%S"
        elapsed = None
        if self.started_at and self.finished_at:
            elapsed = round((self.finished_at - self.started_at).total_seconds(), 1)
        return {
            "id": self.id, "job_type": self.job_type, "status": self.status,
            "params": self.params, "scope_key": self.scope_key,
            "result_summary": self.result_summary,
            "error_msg": self.error_msg,
            "created_by": self.created_by,
            "created_at": self.created_at.strftime(fmt) if self.created_at else None,
            "started_at": self.started_at.strftime(fmt) if self.started_at else None,
            "finished_at": self.finished_at.strftime(fmt) if self.finished_at else None,
            "elapsed_sec": elapsed,
            "timeout_seconds": self.timeout_seconds,
        }
