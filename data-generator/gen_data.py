#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高校学生行为数据采集与可视化系统 —— 模拟数据生成器（data-generator 模块）
==========================================================================

【生成内容】
    1. 学生基础信息        -> student 表
    2. 消费流水（早/中/晚/超市/夜宵） -> consumption 表
    3. 图书馆进出记录      -> library_record 表
    4. 脏数据（is_valid=0，供清洗模块演示）
       异常行为样本（供预警模块演示：突发高额消费 / 连续低消费 / 长期不进馆 / 深夜消费）

【行为规律还原】
    - 三餐时间服从正态分布：早餐峰值 08:00、午餐 12:00、晚餐 18:00
    - 消费金额服从对数正态分布（多数人正常、少数人偏高的右偏长尾）
    - 周末食堂消费频率下降（约 5 折），超市集中采购略升
    - 每名学生有独立潜变量（活跃度 / 学习强度 / 消费水平 / 夜猫子 / 周末离校），
      所有行为由潜变量驱动，保证"个体画像"内部一致、可解释
    - 图书馆工作日双高峰：14:00-16:00、19:00-21:00（混合高斯），
      并叠加期中/期末"学习周"正态峰
    - 单次停留时长 30 分钟 ~ 4 小时，长尾分布

【运行】
    # 小规模演示（答辩现场用，秒级）
    python gen_data.py --students 200 --days 30

    # 论文实验规模：自动延长模拟天数凑够目标行数（不虚构"每人每天十几笔"的假规律）
    python gen_data.py --students 200 --target-consumption 100000 --target-library 50000

    # 先看规律报告、只导 CSV 不写库
    python gen_data.py --students 200 --days 30 --dry-run --csv-dir output

    # 清库重跑（幂等，可反复执行）
    python gen_data.py --truncate --seed 20260922 ...

【MySQL 连接】环境变量或命令行参数二选一
    DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
    注意：meal_period、stay_minutes 是数据库 STORED 生成列，本脚本不写这两列。
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, TextIO, Tuple

import numpy as np
from faker import Faker

try:
    import pymysql
except ImportError:                                  # --dry-run 时允许不装 pymysql
    pymysql = None

# =============================================================================
# 0. 静态配置：学院专业 / 商户 / 时段参数
# =============================================================================

COLLEGES: List[Tuple[str, List[str]]] = [
    ("计算机与人工智能学院", ["软件工程", "计算机科学与技术", "人工智能", "数据科学与大数据技术"]),
    ("电子信息工程学院", ["电子信息工程", "通信工程", "物联网工程"]),
    ("机械工程学院", ["机械设计制造及其自动化", "车辆工程", "工业设计"]),
    ("经济管理学院", ["会计学", "市场营销", "工商管理", "国际经济与贸易"]),
    ("外国语学院", ["英语", "日语", "商务英语"]),
    ("数学与统计学院", ["数学与应用数学", "统计学", "信息与计算科学"]),
    ("艺术设计学院", ["视觉传达设计", "环境设计", "数字媒体艺术"]),
    ("法政学院", ["法学", "行政管理", "社会工作"]),
]
COLLEGE_CODES = {name: f"{i + 1:02d}" for i, (name, _) in enumerate(COLLEGES)}
COLLEGE_WEIGHT = np.array([0.24, 0.16, 0.15, 0.14, 0.08, 0.08, 0.07, 0.08])  # 工科偏多

DORM_BUILDINGS = ["梅园1栋", "梅园2栋", "兰园3栋", "竹园5栋", "菊园6栋", "松园8栋",
                  "紫荆公寓A", "紫荆公寓B"]
GRADE_YEARS = [2021, 2022, 2023, 2024]
GRADE_WEIGHT = np.array([0.20, 0.28, 0.28, 0.24])

CANTEENS = ["第一食堂", "第二食堂", "第三食堂（清真）", "教工风味餐厅", "翡翠湖美食广场"]
SUPERMARKETS = ["校园生活超市", "佰利源超市", "水果便利店", "文印文具店", "洗护用品店"]

# 消费时段模板：时间用"距当日 00:00 的分钟数"表示，便于 numpy 正态采样
#   mu/sigma    就餐时刻正态分布参数
#   lo/hi       该时段的硬边界（裁剪，避免出现凌晨吃早餐）；夜宵例外，见下方说明
#   amt_median  金额对数正态的中位数（元）；amt_sigma 长尾强度
#   base_p      普通学生（activity=1）在工作日出现该类消费的基准概率
#   wk_factor   周末概率倍率（<1 表示频率下降）；wk_shift 周末时刻整体后移（起床晚）
SLOTS: List[Dict] = [
    dict(key="breakfast", name="早餐", mtype=1, mu=8 * 60 + 20, sigma=32, lo=6 * 60 + 30, hi=9 * 60 + 30,
         amt_median=6.0, amt_sigma=0.35, amt_lo=2.0, amt_hi=18.0, base_p=0.82, wk_factor=0.50, wk_shift=115),
    dict(key="lunch", name="午餐", mtype=1, mu=12 * 60 + 10, sigma=38, lo=10 * 60 + 40, hi=13 * 60 + 40,
         amt_median=13.0, amt_sigma=0.30, amt_lo=5.0, amt_hi=35.0, base_p=0.92, wk_factor=0.55, wk_shift=40),
    dict(key="dinner", name="晚餐", mtype=1, mu=18 * 60 + 10, sigma=42, lo=16 * 60 + 30, hi=20 * 60 + 40,
         amt_median=15.0, amt_sigma=0.32, amt_lo=6.0, amt_hi=42.0, base_p=0.90, wk_factor=0.58, wk_shift=15),
    dict(key="supermarket", name="超市", mtype=2, mu=19 * 60 + 30, sigma=150, lo=7 * 60, hi=22 * 60 + 30,
         amt_median=22.0, amt_sigma=0.55, amt_lo=3.0, amt_hi=130.0, base_p=0.30, wk_factor=1.30, wk_shift=0),
    # 夜宵/通宵：真实作息是 22:30 起、可延续到次日凌晨。
    # hi 写成 >1440 的分钟数，由 _clean_rows 里的 timedelta 自然进位到次日凌晨 01:30。
    # 旧值把上界裁在 23:59，使预警口径 23:00-05:00 这 6 小时里只有 1 小时可能有数据，
    # “夜间消费周频次”类规则永远无法触发，聚类的 night_ratio 特征也只统计到 23 点这一小时。
    dict(key="night", name="夜宵", mtype=5, mu=23 * 60 + 40, sigma=70, lo=22 * 60 + 30, hi=25 * 60 + 30,
         amt_median=14.0, amt_sigma=0.35, amt_lo=5.0, amt_hi=45.0, base_p=0.06, wk_factor=1.60, wk_shift=0),
]
SLOT_IDX = {s["key"]: i for i, s in enumerate(SLOTS)}
IS_CANTEEN = np.array([s["mtype"] == 1 for s in SLOTS])   # 用于"周末离校则食堂不命中"

LIB_VENUES = ["中心图书馆", "南苑分馆", "专业资料室"]
LIB_AREAS = ["一号自习区", "二号自习区", "静音研读间", "报刊阅览室", "电子阅览区", "三层开架区"]
LIB_OPEN_MIN = 7 * 60 + 30      # 07:30 开馆
LIB_CLOSE_MIN = 22 * 60 + 30   # 22:30 闭馆
LIB_MAX_IN_MIN = LIB_CLOSE_MIN - 35          # 最晚入馆，保证至少 35 分钟
MEAL_CROSS_POINTS = (12 * 60, 17 * 60 + 30, 18 * 60 + 40)   # 判断"跨餐占座"的时间点


# =============================================================================
# 1. 配置对象
# =============================================================================

@dataclass
class GenConfig:
    seed: int = 20260922
    students: int = 200
    start: date = date(2026, 5, 1)
    days: int = 30
    target_consumption: int = 0          # >0 时自动延长 days 达到该规模
    target_library: int = 0
    max_days: int = 365
    dirty_ratio: float = 0.02            # 脏数据占比（清洗模块演示）
    anomaly_ratio: float = 0.10          # 异常学生占比（预警模块演示）：按 5 类均分，每类约 4 人
    batch_size: int = 5000
    truncate: bool = False
    dry_run: bool = False                # True: 不写库，只出报告/CSV
    csv_dir: Optional[str] = None
    db: Dict[str, object] = field(default_factory=dict)

    @property
    def batch_no(self) -> str:
        """导入批次号：支持按批次校验、清洗统计与回滚"""
        return f"gen_{self.seed}_{self.students}_{self.days}"

    @property
    def write_db(self) -> bool:
        return (not self.dry_run) and pymysql is not None


# =============================================================================
# 2. 学生名单与个体潜变量
# =============================================================================

def gen_students(cfg: GenConfig, fake: Faker, rng: np.random.Generator) -> List[Dict]:
    """学号规则：入学年份(4) + 学院码(2) + 院内序号(3)，如 202203007"""
    n = cfg.students
    c_idx = rng.choice(len(COLLEGES), size=n, p=COLLEGE_WEIGHT / COLLEGE_WEIGHT.sum())
    g_idx = rng.choice(len(GRADE_YEARS), size=n, p=GRADE_WEIGHT / GRADE_WEIGHT.sum())
    # 性别：男生略多。取值必须落在数据字典规定的 1-男 / 2-女 上，不能让 binomial 的
    # 原始输出 0/1 直接入库（0 会被 models.py 的 gender_text 渲染成"未知"，大屏性别
    # 维度与个体画像页的 41.5% 女生全部显示为未知）。
    # 注意此处只做"等价值映射"、不改抽样调用本身：本 rng 同时被后面的 gen_anomaly_plan
    # 使用，而异常名单矩阵决定消费/图书馆数据的生成形态。若换成 rng.random(n) 重新抽样，
    # 底层随机流会移位，全库行为数据将整体重算，已验证过的统计数值全部失效。
    gender = np.where(rng.binomial(1, 0.55, size=n) == 1, 1, 2)   # 1-男 2-女
    dorm = rng.integers(0, len(DORM_BUILDINGS), size=n)

    students: List[Dict] = []
    seq: Dict[Tuple[int, int], int] = {}                   # (年级, 学院) -> 序号
    for i in range(n):
        ci, gi = int(c_idx[i]), int(g_idx[i])
        college, majors = COLLEGES[ci]
        grade = GRADE_YEARS[gi]
        key = (grade, ci)
        seq[key] = seq.get(key, 0) + 1
        no = seq[key]
        major = majors[(no - 1) % len(majors)]             # 学院内轮转，各专业人数均衡
        sid = f"{grade}{COLLEGE_CODES[college]}{no:03d}"
        students.append(dict(
            student_id=sid,
            name=fake.name(),                              # faker 生成中文模拟姓名
            gender=int(gender[i]),                         # 1-男 2-女
            birth_year=grade - 18,
            college=college,
            major=major,
            class_name=f"{major[:4]}{grade % 100}{(no - 1) // 30 + 1}班",
            grade_year=grade,
            dorm_building=DORM_BUILDINGS[int(dorm[i])],
            card_no=f"C{sid}{rng.integers(10, 99)}",
            enroll_status=1,
        ))
    return students


def gen_personas(cfg: GenConfig, n: int) -> Dict[str, np.ndarray]:
    """
    个体行为潜变量 —— 全部下游行为都由它们驱动，因此同一个人的消费与学习记录内在一致：
      activity     总体活跃度（对数正态，多数 0.8~1.2，少数极端懒/极勤）
      study        学习强度（决定进馆频率与停留时长）
      spend        消费水平（金额倍率）
      night_owl    夜猫子（放大夜宵概率、偏好晚间进馆）
      weekend_home 周末离校概率
    """
    rng = np.random.default_rng(cfg.seed + 100)
    return dict(
        activity=np.clip(rng.lognormal(0.0, 0.28, n), 0.35, 2.0),
        study=np.clip(rng.lognormal(0.0, 0.45, n), 0.05, 2.6),
        spend=np.clip(rng.lognormal(0.0, 0.22, n), 0.55, 2.2),
        night_owl=(rng.random(n) < 0.18).astype(int),
        weekend_home=np.clip(rng.beta(2.0, 5.0, n), 0.0, 0.9),
    )


def gen_anomaly_plan(cfg: GenConfig, n: int, days: int,
                     rng: np.random.Generator) -> Dict[str, object]:
    """
    刻意构造"确实异常"的学生，保证预警模块有真实可解释的输出：
      HIGH_CONSUME   某天突发大额消费（600~1500 元）
      LOW_CONSUME    连续 4~6 天几乎不吃饭（疑似节食/经济困难）
      NO_CONSUME     每人两段 4~7 天整日零消费（总纲规则"连续3天无消费"的验证前提）
      NO_LIBRARY     临近期末却连续 15~30 天不进馆
      NIGHT_CONSUME  整期高频深夜消费（夜宵概率放大 3.5 倍，并每夜注入 1~2 笔凌晨交易）
                     —— 后者是总纲规则“夜间消费周频次 >5”能被验证的前提
    用 day×student 布尔矩阵表达，生成时按列取用，避免逐学生 if 判断。

    这5 类名单就是这份数据集的 ground truth：预警模块的准确率/召回率
    可以直接拿命中学号集合与 plan["students"] 对比算出来（论文"规则有效性验证"一节）。
    """
    k = int(round(n * cfg.anomaly_ratio)) if cfg.anomaly_ratio > 0 else 0
    picks = rng.choice(n, size=min(k, n), replace=False) if k else np.array([], dtype=int)
    high = picks[picks % 5 == 0]
    low = picks[picks % 5 == 1]
    no_lib = picks[picks % 5 == 2]
    night = picks[picks % 5 == 3]
    zero = picks[picks % 5 == 4]

    big_buyer_day = {int(s): int(rng.integers(0, days)) for s in high}

    low_mat = np.zeros((days, n), dtype=bool)
    for s in low:
        if days >= 6:
            st = int(rng.integers(0, days - 5))
            low_mat[st: st + int(rng.integers(4, 7)), s] = True

    absent_mat = np.zeros((days, n), dtype=bool)
    for s in no_lib:
        if days >= 10:
            absent_mat[max(0, days - int(rng.integers(15, 30))):, s] = True

    # 与 LOW_CONSUME 的区别是"一笔都没有"：连续低消费仍有流水，零消费是流水整天缺失，
    # 两者在数据上不可混为一谈，总纲规则 1 只认后者
    zero_mat = np.zeros((days, n), dtype=bool)
    for s in zero:
        for _ in range(2):                                # 每人两段窗口，模拟"回家度周末"与"卡片故障"两类成因
            if days >= 6:
                st = int(rng.integers(0, days - 6))
                zero_mat[st: st + int(rng.integers(4, 8)), s] = True

    night_mat = np.zeros((days, n), dtype=bool)
    for s in night:
        night_mat[:, s] = True          # 整期每天都通宵，而不是零星几天：作息异常是习惯不是偶发

    return dict(big_buyer_day=big_buyer_day, low_mat=low_mat, zero_mat=zero_mat,
                absent_mat=absent_mat, night_mat=night_mat,
                students={"high": [int(x) for x in high], "low": [int(x) for x in low],
                          "zero": [int(x) for x in zero],
                          "no_lib": [int(x) for x in no_lib], "night": [int(x) for x in night]})


# =============================================================================
# 3. 消费记录生成器（逐日推进 + 卡内余额顺序结算 + 脏数据注入）
# =============================================================================

class ConsumptionSimulator:
    # 干净行元组顺序严格对应 CONS_COLS
    def __init__(self, cfg: GenConfig, students: List[Dict],
                 personas: Dict[str, np.ndarray], plan: Dict[str, object]):
        self.cfg = cfg
        self.sid = [s["student_id"] for s in students]
        self.p = personas
        self.plan = plan
        self.n = len(students)
        self.rng = np.random.default_rng(cfg.seed + 200)
        self.balance = self.rng.uniform(300, 800, size=self.n)     # 期初一卡通余额
        self.next_topup = self.rng.uniform(300, 500, size=self.n)  # 下次充值金额
        self.terminals = np.array([f"T{c:02d}{i:03d}" for c in range(8) for i in range(120)])

        # 规律自检统计（只统计干净数据，脏数据不污染报告）
        self.stat_hours = np.zeros(24)
        self.stat_slots = np.zeros(len(SLOTS))
        self.stat_rows = np.zeros(2)      # [工作日, 周末]
        self.stat_amount = np.zeros(2)
        self.stat_day_cnt = np.zeros(2)   # 天数，用于算日均
        self.dirty_total = 0

    # ------------------------------------------------------------------
    def gen_day(self, d_idx: int, day: date) -> List[Tuple]:
        rng = self.rng
        is_weekend = day.weekday() >= 5
        self.stat_day_cnt[1 if is_weekend else 0] += 1

        # 1) 逐时段伯努利采样：概率 = 基准 × 周末系数 × 活跃度 ×（夜猫子/离校修正）
        hit_cols = []
        for si, slot in enumerate(SLOTS):
            p = np.full(self.n, slot["base_p"] * (slot["wk_factor"] if is_weekend else 1.0), float)
            p = p * self.p["activity"]
            if slot["key"] == "night":
                boost = np.where(self.plan["night_mat"][d_idx], 3.5,
                                 np.where(self.p["night_owl"] == 1, 2.6, 1.0))
                p = p * boost
            if slot["key"] == "supermarket":
                p = p * self.p["spend"]
            p = np.clip(p, 0.0, 0.97)
            hit = rng.random(self.n) < p
            if is_weekend and IS_CANTEEN[si]:
                hit &= ~(rng.random(self.n) < self.p["weekend_home"])   # 离校者不在食堂吃饭
            hit_cols.append(hit)
        hit_mat = np.column_stack(hit_cols)

        # 2) LOW_CONSUME 异常样本：当天只保留 0~1 笔
        low = self.plan["low_mat"][d_idx]
        if low.any():
            for s in np.nonzero(low)[0]:
                cols = np.nonzero(hit_mat[s])[0]
                keep = np.zeros(hit_mat.shape[1], dtype=bool)
                if cols.size and rng.random() < 0.75:                   # 25% 概率当天完全无消费
                    keep[rng.choice(cols)] = True
                hit_mat[s] = keep

        # 2.5) NO_CONSUME 异常样本：当日一笔不留（必须在所有时段采样完成后整体置空）
        zero = self.plan["zero_mat"][d_idx]
        if zero.any():
            hit_mat[zero] = False

        stu_i, slot_i = np.nonzero(hit_mat)

        # 3) 向量化采样时刻与金额
        rows_u: List[Tuple[int, int, int, float]] = []
        if stu_i.size:
            mu = np.array([SLOTS[i]["mu"] + (SLOTS[i]["wk_shift"] if is_weekend else 0) for i in slot_i], float)
            sg = np.array([SLOTS[i]["sigma"] for i in slot_i], float)
            lo = np.array([SLOTS[i]["lo"] for i in slot_i], float)
            hi = np.array([SLOTS[i]["hi"] for i in slot_i], float)
            if d_idx == self.cfg.days - 1:
                # 末日禁止跨零点：否则部分记录会溢出到统计窗口之外的次日，
                # 趋势图最后一天只剩几十条凌晨记录，看起来像“消费断崖”的数据质量假象
                is_night = np.fromiter((SLOTS[i]["key"] == "night" for i in slot_i), bool, slot_i.size)
                hi = np.where(is_night, np.minimum(hi, 24 * 60 - 1), hi)
            times = np.clip(rng.normal(mu, sg), lo, hi)                 # 正态分布三餐时间

            median = np.array([SLOTS[i]["amt_median"] for i in slot_i], float) * \
                np.clip(self.p["spend"][stu_i], 0.6, 2.0)               # 个人消费水平
            a_sigma = np.array([SLOTS[i]["amt_sigma"] for i in slot_i], float)
            a_lo = np.array([SLOTS[i]["amt_lo"] for i in slot_i], float)
            a_hi = np.array([SLOTS[i]["amt_hi"] for i in slot_i], float)
            amounts = np.clip(rng.lognormal(np.log(median), a_sigma), a_lo, a_hi)  # 对数正态金额

            rows_u = list(zip(stu_i.tolist(), slot_i.tolist(),
                              np.round(times).astype(int).tolist(), amounts.tolist()))

        # 4) HIGH_CONSUME 异常样本：单日突发大额采购
        for s, target in self.plan["big_buyer_day"].items():
            if target == d_idx:
                for _ in range(2):
                    rows_u.append((s, SLOT_IDX["supermarket"],
                                   int(rng.integers(14 * 60, 20 * 60)),
                                   float(rng.uniform(350, 1500))))

        # 5) 通宵型异常样本：每夜 1~2 笔落在 23:00~次日 02:30（全部计入预警口径）。
        #    为什么必须显式注入：普通学生夜宵基准概率 0.06，即使乘 3.5 倍也只有 0.21 笔/天
        #    ≈ 1.5 笔/周，距总纲阈值的“周内 >5 次”差一个量级；不构造长期通宵群体，
        #    规则 4 在这份数据上就是空规则。“一晚两笔”对应“宿舍楼下便利店 + 夜宵摊”的真实链路。
        hard = np.nonzero(self.plan["night_mat"][d_idx])[0]
        if hard.size and d_idx < self.cfg.days - 1:                     # 末日不注入，理由同上
            for s in hard:
                for _ in range(int(rng.binomial(2, 0.75))):             # 期望 1.5 笔/晚
                    rows_u.append((int(s), SLOT_IDX["night"],
                                   int(rng.integers(23 * 60, 26 * 60 + 30)),   # 23:00~02:30
                                   float(rng.uniform(8.0, 32.0))))

        rows = self._clean_rows(day, rows_u)
        return rows + self._make_dirty(rows)

    # ------------------------------------------------------------------
    def _clean_rows(self, day: date, rows_u: List[Tuple[int, int, int, float]]) -> List[Tuple]:
        """按（学生, 时间）排序后顺序结算余额：余额 = 上期余额 - 累计消费 (+自动充值)"""
        if not rows_u:
            return []
        rng = self.rng
        rows_u.sort(key=lambda r: (r[0], r[2]))
        dt0 = datetime(day.year, day.month, day.day)
        rows: List[Tuple] = []
        for s, si, minute, amount in rows_u:
            slot = SLOTS[si]
            if self.balance[s] - amount < 30:                 # 余额不足 -> 触发一次充值
                self.balance[s] += self.next_topup[s]
                self.next_topup[s] = float(rng.uniform(300, 500))
            self.balance[s] -= amount
            ts = dt0 + timedelta(minutes=int(minute))
            rows.append((
                self.sid[s],                    # student_id
                slot["mtype"],                  # merchant_type
                self._merchant(si),             # merchant_name
                round(float(amount), 2),        # amount
                round(float(self.balance[s]), 2),  # balance
                str(rng.choice(self.terminals)),  # terminal_id
                ts,                             # consumed_at
                1,                              # is_valid
                self.cfg.batch_no,              # batch_no
            ))
            self.stat_hours[(minute // 60) % 24] += 1   # 凌晨记录 minute>1439，取模归到 0~2 点
            self.stat_slots[si] += 1
            w = 1 if day.weekday() >= 5 else 0
            self.stat_rows[w] += 1
            self.stat_amount[w] += float(amount)
        return rows

    def _merchant(self, si: int) -> str:
        rng = self.rng
        mtype = SLOTS[si]["mtype"]
        if mtype == 1:
            return f"{CANTEENS[int(rng.integers(len(CANTEENS)))]}{int(rng.integers(1, 4))}楼" \
                   f"{int(rng.integers(1, 13)):02d}号窗口"
        if mtype == 2:
            return SUPERMARKETS[int(rng.integers(len(SUPERMARKETS)))]
        return f"{CANTEENS[int(rng.integers(len(CANTEENS)))]}夜宵档"

    # ------------------------------------------------------------------
    def _make_dirty(self, clean: List[Tuple]) -> List[Tuple]:
        """
        按 dirty_ratio 追加脏数据（is_valid=0，软删除以便论文统计清洗效果）：
          类型1 完全重复行 —— 闸机重传
          类型2 金额为负   —— 退款/冲正未处理
          类型3 金额=0 且时间落在 3 年前 —— 采集器时钟故障
          类型4 孤儿学号   —— 上游脏数据，清洗时需按 student 表左连接识别
        """
        k = int(len(clean) * self.cfg.dirty_ratio)
        if k <= 0:
            return []
        rng = self.rng
        out: List[Tuple] = []
        for j, i in enumerate(rng.choice(len(clean), size=k, replace=False)):
            row = list(clean[int(i)])
            kind = j % 4
            if kind == 1:
                row[3] = -abs(float(row[3]))
            elif kind == 2:
                row[3] = 0.0
                row[6] = row[6] - timedelta(days=3 * 365)
            elif kind == 3:
                row[0] = "299999901"
            row[7] = 0
            out.append(tuple(row))
        self.dirty_total += len(out)
        return out


# =============================================================================
# 4. 图书馆记录生成器（双高峰混合高斯 + 长尾时长 + 同日两场不重叠）
# =============================================================================

class LibrarySimulator:
    def __init__(self, cfg: GenConfig, students: List[Dict],
                 personas: Dict[str, np.ndarray], plan: Dict[str, object]):
        self.cfg = cfg
        self.sid = [s["student_id"] for s in students]
        self.p = personas
        self.plan = plan
        self.n = len(students)
        self.rng = np.random.default_rng(cfg.seed + 300)
        self.stat_hours = np.zeros(24)
        self.durations: List[float] = []
        self.dirty_total = 0
        self.visit_days = 0

    def gen_day(self, d_idx: int, day: date) -> List[Tuple]:
        rng = self.rng
        is_weekend = day.weekday() >= 5
        # 学习强度 = 基准 × 个人 study × 期末/期中考试周正态峰（用 day % 60 模拟一个学期节奏）
        dot = d_idx % 60
        final_peak = 1.0 + 0.55 * math.exp(-((dot - 45) ** 2) / (2 * 12.0 ** 2))
        mid_peak = 1.0 + 0.35 * math.exp(-((dot - 15) ** 2) / (2 * 3.0 ** 2))
        p = 0.33 * self.p["study"] * final_peak * mid_peak
        if is_weekend:
            p = p * 0.55 * (1 - self.p["weekend_home"] * 0.7)
        p = np.clip(p, 0.0, 0.95)
        visits = rng.binomial(2, p)                        # 单日最多 2 次完整进出
        visits[self.plan["absent_mat"][d_idx]] = 0         # NO_LIBRARY 异常样本强制为 0
        total = int(visits.sum())
        if total == 0:
            return []
        self.visit_days += int((visits > 0).sum())

        # 当日第几场：0=首场，1=第二场（用 cumsum 向量化，避免 Python 循环）
        stu_i = np.repeat(np.arange(self.n), visits)
        starts = np.concatenate(([0], np.cumsum(visits)[:-1]))
        seq = np.arange(total) - np.repeat(starts, visits)

        # 入馆时刻：早场 8% + 下午高峰(15:00) 54% + 晚高峰(20:00) 38%
        r = rng.random(total)
        mins = np.where(r < 0.08, rng.normal(9 * 60, 55, total),
                        np.where(r < 0.62, rng.normal(15 * 60, 62, total),
                                 rng.normal(20 * 60, 52, total)))
        # 夜猫子偏好晚场
        mins = mins + np.where(self.p["night_owl"][stu_i] == 1, 25, 0)
        # 第二场从晚间分布重新采样（不用硬下界夹逼，否则会人为堆出尖峰），
        # 同日两场的先后关系交给下面的"防重叠"逻辑处理
        mins = np.where(seq == 0, mins, rng.normal(19 * 60 + 40, 75, total))
        mins = np.clip(mins, LIB_OPEN_MIN, LIB_MAX_IN_MIN)

        # 停留时长：对数正态长尾（中位 95 分钟），裁剪 30~240 分钟
        # sigma 取 0.50：保证触到 4h 上限的比例低于 5%，避免在上限处形成尖峰
        dur = rng.lognormal(math.log(95.0), 0.50, total) * \
            np.clip(self.p["study"][stu_i], 0.6, 1.5)
        dur = np.clip(dur, 30, 240)

        # 分学生处理：同日两场时间排序且不重叠，跨餐且时长>=2h 标记 in_meal_flag
        order = np.lexsort((mins, stu_i))
        stu_s, min_s, dur_s = stu_i[order], mins[order], dur[order]
        dt0 = datetime(day.year, day.month, day.day)
        rows: List[Tuple] = []
        for grp in np.split(np.arange(total), np.flatnonzero(np.diff(stu_s)) + 1):
            buf: List[Tuple[int, float, float]] = []
            prev_out = -1.0
            for k in grp:
                m, du = float(min_s[k]), float(dur_s[k])
                if prev_out > 0 and m < prev_out:
                    m = prev_out + float(rng.integers(15, 61))
                m = min(m, LIB_MAX_IN_MIN)
                du = min(du, LIB_CLOSE_MIN - m)
                if du < 30:
                    continue
                s = int(stu_s[k])
                buf.append((s, m, du))
                prev_out = m + du
            rows.extend(self._emit(buf, dt0))
        return rows + self._make_dirty(rows)

    def _emit(self, buf: List[Tuple[int, float, float]], dt0: datetime) -> List[Tuple]:
        if not buf:
            return []
        rng = self.rng
        rows: List[Tuple] = []
        for s, m, du in buf:
            t_in = dt0 + timedelta(minutes=int(m))
            t_out = t_in + timedelta(minutes=int(du))
            still_in = rng.random() < 0.003            # 0.3% 只刷入未刷出 -> gate_out_time NULL
            cross = du >= 120 and any(m < p < m + du for p in MEAL_CROSS_POINTS)
            rows.append((
                self.sid[s], str(rng.choice(LIB_VENUES)),
                int(rng.integers(1, 6)), str(rng.choice(LIB_AREAS)),
                f"{int(rng.integers(1, 40)):02d}-{int(rng.integers(1, 25)):02d}",
                t_in, None if still_in else t_out,
                1 if cross else 0, 1, self.cfg.batch_no,
            ))
            self.stat_hours[int(m) // 60] += 1
            self.durations.append(du)
        return rows

    def _make_dirty(self, clean: List[Tuple]) -> List[Tuple]:
        """图书馆脏数据：离馆早于入馆 / 时长超 30 小时 / 重复上传，均 is_valid=0"""
        k = int(len(clean) * self.cfg.dirty_ratio)
        if k <= 0:
            return []
        rng = self.rng
        out: List[Tuple] = []
        for j, i in enumerate(rng.choice(len(clean), size=k, replace=False)):
            row = list(clean[int(i)])
            if j % 3 == 0 and row[6] is not None:
                row[6] = row[5] - timedelta(minutes=int(rng.integers(10, 120)))
            elif row[6] is not None:
                row[6] = row[5] + timedelta(minutes=int(rng.integers(2000, 5000)))
            row[8] = 0
            out.append(tuple(row))
        self.dirty_total += len(out)
        return out


# =============================================================================
# 5. 输出：MySQL 批量写入 / CSV 流式导出
# =============================================================================

STUDENT_COLS = ("student_id", "name", "gender", "birth_year", "college", "major",
                "class_name", "grade_year", "dorm_building", "card_no", "enroll_status")
# meal_period 是数据库生成列，不能出现在 INSERT 列清单里
CONS_COLS = ("student_id", "merchant_type", "merchant_name", "amount", "balance",
             "terminal_id", "consumed_at", "is_valid", "batch_no")
# stay_minutes 是数据库生成列，不能出现在 INSERT 列清单里
LIB_COLS = ("student_id", "venue", "floor_no", "area_name", "seat_no",
            "gate_in_time", "gate_out_time", "in_meal_flag", "is_valid", "batch_no")


class TableWriter:
    """攒够 batch_size 行就 executemany，兼顾内存与导入速度"""

    def __init__(self, cfg: GenConfig, table: str, cols: Tuple[str, ...]):
        self.cfg, self.table = cfg, table
        self.buf: List[Tuple] = []
        self.total = 0
        self.conn = None
        self.sql = (f"INSERT INTO {table} ({', '.join(cols)}) "
                    f"VALUES ({', '.join(['%s'] * len(cols))})")
        if cfg.write_db:
            self.conn = pymysql.connect(charset="utf8mb4", autocommit=False, **cfg.db)
            with self.conn.cursor() as cur:
                # 批量导入常规提速；close() 中复原
                cur.execute("SET unique_checks=0")
                cur.execute("SET FOREIGN_KEY_CHECKS=0")
            self.conn.commit()

    def add(self, rows: Iterable[Tuple]):
        self.buf.extend(rows)
        if len(self.buf) >= self.cfg.batch_size:
            self.flush()

    def flush(self):
        if not self.buf:
            return
        self.total += len(self.buf)
        if self.conn is not None:
            with self.conn.cursor() as cur:
                cur.executemany(self.sql, self.buf)
            self.conn.commit()
        self.buf.clear()

    def close(self) -> int:
        self.flush()
        if self.conn is not None:
            with self.conn.cursor() as cur:
                cur.execute("SET FOREIGN_KEY_CHECKS=1")
                cur.execute("SET unique_checks=1")
            self.conn.commit()
            self.conn.close()
        return self.total


def write_students(cfg: GenConfig, students: List[Dict]) -> int:
    """学生表量小，直接 executemany；ON DUPLICATE KEY UPDATE 保证脚本可重复执行"""
    if not cfg.write_db:
        return len(students)
    conn = pymysql.connect(charset="utf8mb4", autocommit=False, **cfg.db)
    sql = ("INSERT INTO student (" + ", ".join(STUDENT_COLS) + ") VALUES ("
           + ", ".join(["%s"] * len(STUDENT_COLS)) + ") ON DUPLICATE KEY UPDATE "
           + ", ".join(f"{c}=VALUES({c})" for c in STUDENT_COLS if c != "student_id"))
    with conn.cursor() as cur:
        cur.executemany(sql, [tuple(s[c] for c in STUDENT_COLS) for s in students])
    conn.commit()
    conn.close()
    return len(students)


def truncate_all(cfg: GenConfig) -> None:
    """清库重跑：先子表后父表（临时关外键检查，顺序无关）"""
    if not cfg.write_db:
        return
    conn = pymysql.connect(charset="utf8mb4", autocommit=False, **cfg.db)
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in ("warning", "library_record", "consumption", "student"):
            cur.execute(f"TRUNCATE TABLE {t}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    conn.close()
    print("[clean] 已清空 student / consumption / library_record / warning")


class CsvSink:
    """CSV 流式导出，避免大数据量时全表驻留内存"""

    def __init__(self, cfg: GenConfig, name: str, cols: Tuple[str, ...]):
        self.path = os.path.join(cfg.csv_dir, name) if cfg.csv_dir else None
        self.f: Optional[TextIO] = None
        self.w = None
        self.n = 0
        if self.path:
            os.makedirs(cfg.csv_dir, exist_ok=True)
            self.f = open(self.path, "w", newline="", encoding="utf-8-sig")
            self.w = csv.writer(self.f)
            self.w.writerow(cols)

    def add(self, rows: List[Tuple]):
        if self.w and rows:
            self.w.writerows(rows)
            self.n += len(rows)

    def close(self):
        if self.f:
            self.f.close()
            print(f"[csv ] {self.path}  {self.n} 行")


# =============================================================================
# 6. 规律自检报告（论文"数据合理性验证"章节可直接引用这些数字）
# =============================================================================

def _bar(v: float, vmax: float) -> str:
    return "#" * int(round(v / vmax * 46)) if vmax else ""


def report(cfg: GenConfig, sc: ConsumptionSimulator, sl: LibrarySimulator,
           n_cons: int, n_lib: int) -> None:
    line = "=" * 72
    print(f"\n{line}\n模拟数据规律自检报告\n{line}")
    end = cfg.start + timedelta(days=cfg.days - 1)
    print(f"配置   students={cfg.students} days={cfg.days} seed={cfg.seed} 窗口 {cfg.start} ~ {end}")
    print(f"总量   学生 {cfg.students} | 消费 {n_cons}（含脏 {sc.dirty_total}）"
          f" | 图书馆 {n_lib}（含脏 {sl.dirty_total}）")

    print("\n[1] 消费时刻 24 小时分布（应见 8/12/18 三餐峰，以及 23 点主峰 + 0~1 点凌晨尾巴）")
    vmax = sc.stat_hours.max()
    for h in range(24):
        v = int(sc.stat_hours[h])
        if v:
            print(f"    {h:02d}:00 {v:>7} {_bar(v, vmax)}")
    print(f"    -> 最高峰小时 = {int(np.argmax(sc.stat_hours)):02d}:00")

    print("\n[2] 消费类型构成（三餐/超市/夜宵占比）")
    tot = sc.stat_slots.sum()
    for si, cnt in enumerate(sc.stat_slots):
        print(f"    {SLOTS[si]['name']:<5}{int(cnt):>7}  {cnt / tot * 100:5.1f}%")

    wd, we = sc.stat_rows
    if wd and we:
        d_wd, d_we = max(1, sc.stat_day_cnt[0]), max(1, sc.stat_day_cnt[1])
        rate_wd, rate_we = wd / d_wd / cfg.students, we / d_we / cfg.students
        print("\n[3] 工作日 vs 周末（人均日消费笔数应显著下降）")
        print(f"    工作日：人均 {rate_wd:.2f} 笔/天，单笔均值 {sc.stat_amount[0] / wd:.2f} 元")
        print(f"    周  末：人均 {rate_we:.2f} 笔/天，单笔均值 {sc.stat_amount[1] / we:.2f} 元")
        print(f"    -> 周末频率降幅 {(1 - rate_we / rate_wd) * 100:.1f}%")

    print("\n[4] 图书馆进馆时刻分布（应见 14-16 与 19-21 双高峰）")
    vmax = sl.stat_hours.max()
    for h in range(24):
        v = int(sl.stat_hours[h])
        if v:
            print(f"    {h:02d}:00 {v:>7} {_bar(v, vmax)}")
    if sl.durations:
        d = np.array(sl.durations)
        print(f"    单次时长：最短 {d.min():.0f} / 中位 {np.median(d):.0f} / "
              f"均值 {d.mean():.1f} / P95 {np.percentile(d, 95):.0f} / 最长 {d.max():.0f} 分钟")
        print(f"    进馆率：{sl.visit_days / max(1, cfg.days * cfg.students) * 100:.1f}% 学生-日有一次以上进馆")

    print("\n[5] 异常样本（预警模块应能识别以下学生）")
    st = sc.plan["students"]
    for label, ids in (("HIGH_CONSUME 突发大额", st["high"]),
                       ("LOW_CONSUME  连续低消费", st["low"]),
                       ("NO_CONSUME   连续零消费", st["zero"]),
                       ("NO_LIBRARY   长期不进馆", sl.plan["students"]["no_lib"]),
                       ("NIGHT_*  深夜/通宵消费", st["night"])):
        names = [sc.sid[i] for i in ids[:6]]
        print(f"    {label:<24} {len(ids):>3} 人  示例学号: {', '.join(names)}")
    print(line + "\n")


# =============================================================================
# 7. main
# =============================================================================

EST_ROWS_PER_DAY = {"consumption": 2.45, "library": 0.72}   # 实测：每人每日平均行数


def resolve_days(cfg: GenConfig) -> None:
    """
    按目标行数自动延长模拟天数。
    设计原则：绝不靠"拔高每人每天笔数"凑量（那会破坏行为规律、导致画像失真），
    只能拉长时间窗口或增大样本人数，所以目标行数必须是"可达成"的。
    实测行为比 consumption:library ≈ 3.4:1，与"10万 : 5万"（2:1）并不一致，
    此时两目标无法同时满足，这里给出明确告警与实际可达量估算。
    """
    s = max(1, cfg.students)
    need_c = math.ceil(cfg.target_consumption / (s * EST_ROWS_PER_DAY["consumption"])) \
        if cfg.target_consumption > 0 else cfg.days
    need_l = math.ceil(cfg.target_library / (s * EST_ROWS_PER_DAY["library"])) \
        if cfg.target_library > 0 else cfg.days
    need = max(need_c, need_l)

    if cfg.target_consumption > 0 and cfg.target_library > 0 and abs(need_c - need_l) > 0.2 * max(need_c, need_l):
        print(f"[warn] 目标规模冲突：消费需 {need_c} 天、图书馆需 {need_l} 天才能达成。\n"
              f"       实测行为比 消费:图书馆 ≈ 1:{EST_ROWS_PER_DAY['library'] / EST_ROWS_PER_DAY['consumption']:.2f}，"
              f"而目标比是 {cfg.target_consumption}:{cfg.target_library}。\n"
              f"       只能取较大值 {min(need, cfg.max_days)} 天（先满足大的那个），或改用 --students 扩大样本。")

    if need > cfg.days:
        days = min(need, cfg.max_days)
        print(f"[scale] 目标规模需 {need} 天（原 {cfg.days} 天）-> 自动延长为 {days} 天，"
              f"预计 消费 ≈ {int(s * days * EST_ROWS_PER_DAY['consumption'])} 行、"
              f"图书馆 ≈ {int(s * days * EST_ROWS_PER_DAY['library'])} 行")
        cfg.days = days


def parse_args(argv=None) -> GenConfig:
    ap = argparse.ArgumentParser(description="高校学生行为数据模拟生成器",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--seed", type=int, default=20260922, help="随机种子，固定即可完全复现")
    ap.add_argument("--students", type=int, default=200)
    ap.add_argument("--days", type=int, default=30, help="模拟天数（指定 target 时会被自动放大）")
    ap.add_argument("--start", type=str, default=None, help="起始日期 YYYY-MM-DD")
    ap.add_argument("--target-consumption", type=int, default=0, help="目标消费行数")
    ap.add_argument("--target-library", type=int, default=0, help="目标图书馆行数")
    ap.add_argument("--dirty-ratio", type=float, default=0.02, help="脏数据比例")
    ap.add_argument("--anomaly-ratio", type=float, default=0.10, help="异常学生比例（5 类均分）")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--truncate", action="store_true", help="导入前清空旧数据")
    ap.add_argument("--dry-run", action="store_true", help="不写库，只出报告/CSV")
    ap.add_argument("--csv-dir", type=str, default=None, help="额外导出 CSV 的目录")
    ap.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--db-user", default=os.getenv("DB_USER", "root"))
    ap.add_argument("--db-password", default=os.getenv("DB_PASSWORD", "123456"))
    ap.add_argument("--db-name", default=os.getenv("DB_NAME", "student_behavior"))
    a = ap.parse_args(argv)

    cfg = GenConfig(seed=a.seed, students=a.students, days=a.days,
                    target_consumption=a.target_consumption, target_library=a.target_library,
                    dirty_ratio=a.dirty_ratio, anomaly_ratio=a.anomaly_ratio,
                    batch_size=a.batch_size, truncate=a.truncate, dry_run=a.dry_run, csv_dir=a.csv_dir)
    if a.start:
        cfg.start = datetime.strptime(a.start, "%Y-%m-%d").date()
    if not a.dry_run:
        cfg.db = dict(host=a.db_host, port=a.db_port, user=a.db_user,
                      password=a.db_password, database=a.db_name)
    return cfg


def main(argv=None) -> int:
    t0 = time.time()
    cfg = parse_args(argv)
    if not cfg.dry_run and pymysql is None:
        print("[error] 未安装 pymysql：pip install pymysql；或加 --dry-run 只生成 CSV", file=sys.stderr)
        return 2
    resolve_days(cfg)

    fake = Faker("zh_CN")
    Faker.seed(cfg.seed)                                   # faker 与 numpy 同时定种子 => 完全可复现
    rng = np.random.default_rng(cfg.seed + 500)

    print(f"[gen ] 生成 {cfg.students} 名学生 ...")
    students = gen_students(cfg, fake, rng)
    personas = gen_personas(cfg, len(students))
    plan = gen_anomaly_plan(cfg, len(students), cfg.days, rng)

    sc = ConsumptionSimulator(cfg, students, personas, plan)
    sl = LibrarySimulator(cfg, students, personas, plan)

    if cfg.truncate:
        truncate_all(cfg)
    print(f"[db  ] student 写入 {write_students(cfg, students)} 行")

    cons_w, lib_w = TableWriter(cfg, "consumption", CONS_COLS), TableWriter(cfg, "library_record", LIB_COLS)
    cons_csv = CsvSink(cfg, "consumption.csv", CONS_COLS)
    lib_csv = CsvSink(cfg, "library_record.csv", LIB_COLS)
    stu_csv = CsvSink(cfg, "student.csv", STUDENT_COLS)
    stu_csv.add([tuple(s[c] for c in STUDENT_COLS) for s in students])
    stu_csv.close()

    for d in range(cfg.days):
        day = cfg.start + timedelta(days=d)
        cons = sc.gen_day(d, day)
        lib = sl.gen_day(d, day)
        cons_w.add(cons)
        lib_w.add(lib)
        cons_csv.add(cons)
        lib_csv.add(lib)
        if (d + 1) % 10 == 0 or d == cfg.days - 1:
            print(f"[gen ] {d + 1}/{cfg.days} 天，累计消费 {cons_w.total + len(cons_w.buf)}"
                  f" / 图书馆 {lib_w.total + len(lib_w.buf)}")

    n_cons, n_lib = cons_w.close(), lib_w.close()
    cons_csv.close()
    lib_csv.close()
    if cfg.write_db:
        print(f"[db  ] consumption {n_cons} 行 / library_record {n_lib} 行 -> {cfg.db.get('database')}")
    report(cfg, sc, sl, n_cons, n_lib)
    print(f"[done] 耗时 {time.time() - t0:.1f}s，批次号 {cfg.batch_no}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
