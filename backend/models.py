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
    warning_type = db.Column(db.String(30), nullable=False, comment="consume/study/health（冗余，免回表）")
    warning_level = db.Column(db.SmallInteger, nullable=False, default=2, comment="1-低 2-中 3-高")
    warning_date = db.Column(db.Date, nullable=False, comment="业务日期")
    metric_value = db.Column(db.Numeric(12, 2), comment="触发时指标值")
    detail_json = db.Column(db.JSON, comment="证据快照")
    message = db.Column(db.String(255), nullable=False, comment="预警文案")
    status = db.Column(db.SmallInteger, nullable=False, default=0, comment="0-未处理 1-已处理 2-已忽略")
    handled_by = db.Column(db.String(50), comment="处理人")
    handled_at = db.Column(db.DateTime, comment="处理时间")
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
            "rule_name": self.rule.rule_name if self.rule else self.rule_code,
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
        }
