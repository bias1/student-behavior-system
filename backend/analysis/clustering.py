# -*- coding: utf-8 -*-
"""
分析层：K-Means 学生画像聚类（scikit-learn）

流程：行为特征构建 -> 标准化 -> K-Means -> 簇命名 -> PCA 降维供散点图
要点：
1. 特征全部按"人均日/率"口径构造，避免总消费被"在校天数不同"带偏。
2. 必须标准化：日均消费(几十元)与在馆分钟(几十分)量纲不同，
   不标准化则欧氏距离完全被大变量主导，聚类结果无意义。
3. 簇命名用"中心特征规则"而不是人工看，保证可复现；命名结果随接口给前端。
4. 聚类开销大且结果稳定，做进程内 TTL 缓存（窗口/K/特征集均参与缓存 key）。
5. 两套特征集（论文里可做特征消融对比）：
   core = 毕设总纲要求的 4 个特征（日均消费/消费频次/日均在馆时长/消费时间标准差）
   full = 在 core 上扩展作息、三餐规律、周末留校等细分行为特征，共 11 个
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from models import db

# 特征定义：key -> (中文名, 单位, 方向说明)。前端图表标签直接用它，保证前后端口径一致
# 前 4 个是毕设总纲明确要求的特征（归入 core 特征集），后 7 个是细分补充特征
FEATURES: Dict[str, Dict[str, str]] = {
    "avg_daily_amount":  {"label": "日均消费", "unit": "元", "desc": "消费水平；窗口总消费 / 窗口天数"},
    "avg_daily_records": {"label": "日均消费频次", "unit": "笔", "desc": "消费习惯活跃度；窗口笔数 / 窗口天数"},
    "avg_daily_study_minutes": {"label": "日均图书馆时长", "unit": "分钟", "desc": "在馆总分钟 / 窗口天数（未进馆当日计 0）"},
    "meal_time_std":     {"label": "消费时间标准差", "unit": "分钟", "desc": "早/中/晚各餐消费时刻的组内标准差再取均值，越小越规律"},
    "amount_cv":         {"label": "消费波动", "unit": "CV", "desc": "日消费的离散程度，越大越不稳定"},
    "night_ratio":       {"label": "深夜消费率", "unit": "%", "desc": "23:00-05:00 消费占比，作息紊乱信号"},
    "meal_reg":          {"label": "三餐规律率", "unit": "%", "desc": "一天内早中晚都出现的比例"},
    "weekend_ratio":     {"label": "周末消费率", "unit": "%", "desc": "周末消费笔数占比，留校强度代理指标"},
    "library_days_ratio": {"label": "进馆天数率", "unit": "%", "desc": "统计期内有进馆的天数占比"},
    "avg_stay_minutes":  {"label": "单次在馆时长", "unit": "分钟", "desc": "单次停留时长均值"},
    "evening_study_ratio": {"label": "晚间进馆率", "unit": "%", "desc": "18 点后进馆占比，夜习型信号"},
}
FEATURE_KEYS = list(FEATURES.keys())

# 特征集：core 是毕设总纲明确要求的 4 维，full 是其超集（同一套取数代码，只换列切片）
FEATURE_SETS: Dict[str, List[str]] = {
    "core": ["avg_daily_amount", "avg_daily_records", "avg_daily_study_minutes", "meal_time_std"],
    "full": FEATURE_KEYS,
}
DEFAULT_FEATURE_SET = "full"


def normalize_feature_set(raw: Any) -> str:
    """白名单解析特征集参数：非法值退回默认，绝不允许把外部字符串当列名用"""
    return raw if raw in FEATURE_SETS else DEFAULT_FEATURE_SET


# 簇命名模板：按"特征优势"打分后贪心指派，保证同名不重复分配
# 权重只用 z 分数的方向，不依赖具体阈值；一行规则对应一类可解释的行为画像
# sets 声明该规则在哪个特征集下可用：引用列不全时整套跳过，避免"零向量规则"抢注到随机簇上
LABEL_RULES: List[Dict[str, Any]] = [
    # ---------- 仅依赖 core 4 维即可成立的画像 ----------
    {"label": "图书馆重度用户", "sets": ("core", "full"),
     "desc": "日均在馆时长远高于均值，学习强度主导画像",
     "prefer": {"avg_daily_study_minutes": 1.3, "avg_daily_amount": -0.2, "avg_daily_records": -0.3}},
    {"label": "高消费低频型", "sets": ("core",),
     "desc": "日均消费高但笔数少，单次金额大（囤货式采购）",
     "prefer": {"avg_daily_amount": 1.0, "avg_daily_records": -0.9, "avg_daily_study_minutes": -0.3}},
    {"label": "低消费高频型", "sets": ("core",),
     "desc": "笔数多但金额低，小额多次消费习惯",
     "prefer": {"avg_daily_records": 1.0, "avg_daily_amount": -0.8, "avg_daily_study_minutes": 0.2}},
    # 实测中日均金额与日均笔数高度正相关（活跃的人两者都高），
    # 所以"高消费低频型"很少被指派，真正出现的是下面这类"双高"画像——
    # 缺了这条规则，双高簇会被权重更大的"消费时间不规律型"误抢（见 KEY_MIN_Z 说明）。
    {"label": "高消费高频型", "sets": ("core", "full"),
     "desc": "日均消费金额与笔数同时偏高，在校消费活跃",
     "prefer": {"avg_daily_amount": 1.0, "avg_daily_records": 1.0,
                "avg_daily_study_minutes": -0.6}},
    {"label": "消费时间不规律型", "sets": ("core", "full"),
     "desc": "三餐时刻离散大（消费时间标准差高），吃饭时间不固定",
     "prefer": {"meal_time_std": 1.3, "avg_daily_study_minutes": -0.3}},
    {"label": "均衡学习型", "sets": ("core", "full"),
     "desc": "消费中等且时间规律，在馆时长不低于均值",
     "prefer": {"avg_daily_study_minutes": 0.6, "meal_time_std": -0.9,
                "avg_daily_amount": 0.2, "avg_daily_records": 0.2}},
    {"label": "低活跃型", "sets": ("core", "full"),
     "desc": "消费、频次、在馆时长均明显低于均值，需关注",
     "prefer": {"avg_daily_amount": -0.8, "avg_daily_records": -0.7,
                "avg_daily_study_minutes": -1.0, "meal_time_std": 0.4}},
    # ---------- 需要 full 集的细分作息/行为特征 ----------
    {"label": "勤奋学习型", "sets": ("full",),
     "desc": "进馆频繁、日均在馆时长高，消费规律",
     "prefer": {"library_days_ratio": 1.0, "avg_daily_study_minutes": 0.8, "meal_reg": 0.4}},
    {"label": "作息紊乱型", "sets": ("full",),
     "desc": "深夜消费明显偏高、晚间自习偏低",
     # 不用 amount_cv 判"作息紊乱"：消费波动高也可能是突发采购，与作息无关
     "prefer": {"night_ratio": 1.3, "meal_reg": -0.5, "evening_study_ratio": -0.5}},
    {"label": "饮食不规律型", "sets": ("full",),
     "desc": "三餐规律度低（经常漏吃早/中/晚某一餐），但深夜消费并不突出",
     "prefer": {"meal_reg": -1.3, "night_ratio": -0.4, "weekend_ratio": 0.3}},
    {"label": "高消费波动型", "sets": ("full",),
     "desc": "消费水平与日间波动都明显偏高，含突发大额采购行为",
     "prefer": {"avg_daily_amount": 1.0, "amount_cv": 0.9, "night_ratio": -0.3}},
    {"label": "舒适宅居型", "sets": ("full",),
     "desc": "消费水平偏高、进馆偏低，周末留校强度高",
     "prefer": {"avg_daily_amount": 0.6, "library_days_ratio": -0.9, "weekend_ratio": 0.5}},
    {"label": "均衡普通型", "sets": ("full",),
     "desc": "三餐较规律、消费频次略高，其余指标在常规区间内",
     "prefer": {"meal_reg": 0.7, "avg_daily_amount": 0.3, "library_days_ratio": 0.3}},
]


# 命名门槛：每条规则权重绝对值最大的特征就是该标签的"立论依据"（关键特征）。
# 只有关键特征的簇中心 z 分数与规则同向、且幅度 >= KEY_MIN_Z 个标准差时才允许指派。
# 不加这道门槛会出现文字与数据矛盾：例如某簇消费时间标准差只比均值高 0.25σ（几乎看不出差别），
# 却因为该规则权重最高而被命名成"消费时间不规律型"，答辩时一问就露馅。
KEY_MIN_Z = 0.4


def rules_for(feature_set: str) -> List[Dict[str, Any]]:
    """取当前特征集可用的命名规则，并按可用列过滤权重"""
    cols = set(FEATURE_SETS[feature_set])
    out = []
    for r in LABEL_RULES:
        if feature_set not in r["sets"]:
            continue
        prefer = {k: w for k, w in r["prefer"].items() if k in cols}
        if len(prefer) >= 2:            # 只剩一个权重时区分度不够，不纳入
            out.append({**r, "prefer": prefer})
    return out


def rule_desc(label: str, rules: List[Dict[str, Any]]) -> str:
    """根据簇标签回查规则的定义文字（该画像的通用含义，与具体数据无关）"""
    return next((r["desc"] for r in rules if r["label"] == label), "")


def describe_cluster(z_row: pd.Series) -> str:
    """
    生成簇说明：完全由该簇自己的 z 分数拼出来，不做任何主观判断。
    这样"簇特征均值表"和"簇文字说明"必然同源，接口给前端的文案不会与数据打架。
    """
    items = sorted(((fk, float(v)) for fk, v in z_row.items()), key=lambda kv: -abs(kv[1]))
    parts = [f"{FEATURES[fk]['label']}{('显著偏高' if v > 0 else '显著偏低')}"
             f"（{v:+.1f}σ）" for fk, v in items if abs(v) >= KEY_MIN_Z]
    if not parts:
        return "各项行为特征均接近全校均值，属普通群体"
    weak = [fk for fk, v in items if abs(v) < KEY_MIN_Z]
    tail = f"；其余{len(weak)}项接近均值" if weak else ""
    return "、".join(parts[:3]) + tail

_CACHE: Dict[int, Dict[str, Any]] = {}
_FEAT_CACHE: Dict[tuple, Dict[str, Any]] = {}   # 特征表级缓存：同一窗口的聚类/手肘/群体均值共用
_LOCK = threading.Lock()


# =============================================================================
# 1. 特征构建
# =============================================================================

def _fetch_daily(start: str, end: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    按 (学生, 天) 取两张聚合表，另取一份 (学生, 餐段) 的消费时刻离散度，
    特征在 pandas 里二次聚合，逻辑更清晰。
    深夜口径与预警规则 NIGHT_CONSUME 严格一致（23:00-05:00）：
    两处定义不同的话，聚类特征里的"深夜率"和预警里的"深夜消费"会相互矛盾。
    """
    cons = pd.read_sql(text("""
        SELECT student_id, DATE(consumed_at) AS d,
               SUM(amount)                                                        AS amt,
               COUNT(*)                                                           AS n,
               SUM(CASE WHEN HOUR(consumed_at) >= 23 OR HOUR(consumed_at) < 5 THEN 1 ELSE 0 END) AS night,
               MAX(meal_period = '早餐')                                          AS has_b,
               MAX(meal_period = '午餐')                                          AS has_l,
               MAX(meal_period = '晚餐')                                          AS has_d,
               MAX(WEEKDAY(consumed_at) >= 5)                                     AS is_we
        FROM consumption
        WHERE is_valid = 1 AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY student_id, d
        """), con=db.engine, params={"start": start, "end": end})

    lib = pd.read_sql(text("""
        SELECT student_id, DATE(gate_in_time) AS d,
               COUNT(*)                                                       AS visits,
               SUM(stay_minutes)                                              AS mins,
               MAX(HOUR(gate_in_time) >= 18)                                  AS is_evening
        FROM library_record
        WHERE is_valid = 1 AND stay_minutes IS NOT NULL
          AND gate_in_time >= :start AND gate_in_time < DATE_ADD(:end, INTERVAL 1 DAY)
        GROUP BY student_id, d
        """), con=db.engine, params={"start": start, "end": end})

    # 消费时间规律性（总纲要求特征）：先按 (学生, 餐段) 算消费时刻的组内标准差，
    # 再对三个餐段取均值，得到"该生吃饭时间有多固定"的单一标量（单位：分钟）。
    # 为何不直接对全天所有流水算标准差：三餐是双峰分布，整体 std 会被峰间距离主导，
    # 偶尔不吃午餐的人反而可能得到更小的 std；分餐段算才能刻画"每顿几点吃"的漂移。
    # HAVING >= 2 排除只有一笔的餐段（样本量为 1 时 std 恒为 0，会人为拉低离散度）。
    meal_std = pd.read_sql(text("""
        SELECT student_id, AVG(md) AS meal_time_std
        FROM (SELECT student_id, meal_period,
                     STDDEV_POP(TIME_TO_SEC(consumed_at) / 60) AS md
              FROM consumption
              WHERE is_valid = 1 AND meal_period IN ('早餐', '午餐', '晚餐')
                AND consumed_at >= :start AND consumed_at < DATE_ADD(:end, INTERVAL 1 DAY)
              GROUP BY student_id, meal_period
              HAVING COUNT(*) >= 2) t
        GROUP BY student_id
        """), con=db.engine, params={"start": start, "end": end})
    return cons, lib, meal_std


def build_features(start: str, end: str, use_cache: bool = True, ttl: int = 600) -> pd.DataFrame:
    """
    返回 index=student_id、columns=FEATURE_KEYS 的完整特征表（11 列）。
    分母统一用窗口天数 window_days，保证"没去吃饭/没去图书馆"这些缺失本身也是信号。
    需要子集时由调用方按 FEATURE_SETS 切片，不在这里做分支，保证两套特征数值一致。
    结果按 (start, end) 做 TTL 缓存（只读约定，调用方只切片/聚合不改原表）：
    个体画像一页会碰 fit_kmeans + group_summary 两次，审计发现"注释说复用缓存、
    实际 group_summary 重新扫表"，缓存在这层补齐后两处天然同源。
    """
    key = (start, end)
    if use_cache:
        with _LOCK:
            hit = _FEAT_CACHE.get(key)
            if hit and time.time() < hit["exp"]:
                return hit["data"]
    cons, lib, meal_std = _fetch_daily(start, end)
    days = pd.read_sql(text("SELECT DATEDIFF(:end, :start) + 1 AS d"), con=db.engine,
                       params={"start": start, "end": end}).iloc[0]["d"]
    window_days = max(1, int(days))

    students = pd.read_sql(text("SELECT student_id FROM student"), con=db.engine)
    df = students.set_index("student_id")

    if len(cons):
        g = cons.groupby("student_id")
        df["total_amount"] = g["amt"].sum()
        df["cons_days"] = g["d"].nunique()
        df["cons_records"] = g["n"].sum()
        df["night_records"] = g["night"].sum()
        df["weekend_records"] = g["is_we"].sum()
        df["all3_days"] = (cons.assign(all3=cons[["has_b", "has_l", "has_d"]].all(axis=1))
                           .groupby("student_id")["all3"].sum())
        # 变异系数 CV = std/mean：只用"有消费的天"计算，衡量消费习惯稳定性
        df["amount_mean"] = g["amt"].mean()
        df["amount_std"] = g["amt"].std().fillna(0)
    else:
        for c in ["total_amount", "cons_days", "cons_records", "night_records",
                  "weekend_records", "all3_days", "amount_mean", "amount_std"]:
            df[c] = 0

    if len(lib):
        gl = lib.groupby("student_id")
        df["lib_days"] = gl["d"].nunique()
        df["lib_visits"] = gl["visits"].sum()
        df["lib_minutes"] = gl["mins"].sum()
        df["lib_evening_visits"] = gl["is_evening"].sum()
    else:
        for c in ["lib_days", "lib_visits", "lib_minutes", "lib_evening_visits"]:
            df[c] = 0

    # ---- 组装最终特征（缺失学生一律补 0，代表"该行为完全没发生"）----
    f = pd.DataFrame(index=df.index)
    f["avg_daily_amount"] = df["total_amount"] / window_days
    f["avg_daily_records"] = df["cons_records"] / window_days        # 日均消费频次（笔）
    f["avg_daily_study_minutes"] = df["lib_minutes"] / window_days    # 日均图书馆时长（分钟）
    f["amount_cv"] = (df["amount_std"] / df["amount_mean"].replace(0, np.nan)).fillna(0)
    f["night_ratio"] = df["night_records"] / df["cons_records"].replace(0, np.nan)
    f["meal_reg"] = df["all3_days"] / df["cons_days"].replace(0, np.nan)
    f["weekend_ratio"] = df["weekend_records"] / df["cons_records"].replace(0, np.nan)
    f["library_days_ratio"] = df["lib_days"] / window_days
    f["avg_stay_minutes"] = df["lib_minutes"] / df["lib_visits"].replace(0, np.nan)
    f["evening_study_ratio"] = df["lib_evening_visits"] / df["lib_visits"].replace(0, np.nan)
    f = f.fillna(0.0)

    # 消费时间标准差：三餐流水不足的学生算不出来（NaN）。
    # 用 0 填会被误读成"极其规律"，用大值填又会被误读成"极度混乱"，
    # 所以用群体中位数填补（不奖不惩），并在论文中说明该处理；全群都缺时兜底 0。
    f["meal_time_std"] = meal_std.set_index("student_id")["meal_time_std"].reindex(f.index)
    f["meal_time_std"] = f["meal_time_std"].fillna(f["meal_time_std"].median()).fillna(0.0)

    # 比率类特征统一换成百分数，前端展示与论文表格更直观
    for k in ["night_ratio", "meal_reg", "weekend_ratio", "library_days_ratio", "evening_study_ratio"]:
        f[k] = f[k] * 100
    f["amount_cv"] = f["amount_cv"] * 100
    if use_cache:
        with _LOCK:
            _FEAT_CACHE[key] = {"data": f[FEATURE_KEYS], "exp": time.time() + ttl}
            if len(_FEAT_CACHE) > 16:            # 防止历史窗口组合把内存撑爆
                oldest = min(_FEAT_CACHE, key=lambda x: _FEAT_CACHE[x]["exp"])
                _FEAT_CACHE.pop(oldest, None)
    return f[FEATURE_KEYS]


# =============================================================================
# 2. 聚类
# =============================================================================

def _name_clusters(centers_z: pd.DataFrame,
                   rules: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """
    簇命名：对标准化后的簇中心（行=簇、列=特征），按命名规则打分做贪心指派。
    用 z 符号而不是硬阈值判断，规则少、可解释、不随数据规模漂移；
    再用关键特征门槛（KEY_MIN_Z）滤掉"依据不足"的指派，宁可留作"群体N"也不硬贴标签。
    注意循环终止条件：早期版本用 shape[1]（特数）当簇数，导致 k < 规则数时
    矩阵全被置为 -inf 后仍在取 argmax，集合不再增长——死循环卡死接口。
    现在按 shape[0] 判定簇数，并在候选耗尽时提前 break。
    """
    rules = rules if rules is not None else LABEL_RULES
    n_clusters = centers_z.shape[0]                     # 行是簇，列是特征
    if not rules or n_clusters == 0:                     # 无规则可用时直接给编号名，不进贪心循环
        return [f"群体{i + 1}" for i in range(n_clusters)]
    Z = centers_z.to_numpy(float)
    score_mat = np.full((len(rules), n_clusters), -np.inf)   # (规则数, 簇数)，-inf 表示不可指派
    for ri, rule in enumerate(rules):
        prefer = {fk: w for fk, w in rule["prefer"].items() if fk in centers_z.columns}
        if not prefer:
            continue
        # 打分 = Σ(z × 权重)，即"该簇在这个画像方向上偏离均值多少"
        w_vec = np.array([prefer.get(fk, 0.0) for fk in centers_z.columns], dtype=float)
        vec = Z @ w_vec
        # 关键特征（权重绝对值最大者）必须同向且偏离够大，否则这条标签不成立
        key_i = int(np.argmax(np.abs(w_vec)))
        kz = Z[:, key_i]
        qualified = (np.sign(kz) == np.sign(w_vec[key_i])) & (np.abs(kz) >= KEY_MIN_Z)
        score_mat[ri, qualified] = vec[qualified]
    labels = [""] * n_clusters
    used_rules, used_clusters = set(), set()
    # 反复取"全局最高分"配对，规则与簇各只能用一次
    while len(used_clusters) < n_clusters and len(used_rules) < len(rules):
        r, c = np.unravel_index(np.argmax(score_mat), score_mat.shape)
        if not np.isfinite(score_mat[r, c]):             # 已无可指派的候选
            break
        labels[c] = rules[r]["label"]
        used_rules.add(r)
        used_clusters.add(c)
        score_mat[r, :] = -np.inf
        score_mat[:, c] = -np.inf
    for i in range(len(labels)):                        # 规则数少于簇数时兜底
        if not labels[i]:
            labels[i] = f"群体{i + 1}"
    return labels


def fit_kmeans(start: str, end: str, k: int = 4, use_cache: bool = True,
               ttl: int = 600, feature_set: str = DEFAULT_FEATURE_SET) -> Dict[str, Any]:
    """
    主入口：返回前端可直接渲染的聚类结果（含簇统计、逐学生归类表、散点坐标、评估指标）。
    feature_set："core"（总纲要求的 4 特征）或 "full"（11 特征），两者共用同一套取数与命名代码。
    """
    feature_set = normalize_feature_set(feature_set)
    cols = FEATURE_SETS[feature_set]
    rules = rules_for(feature_set)
    key = hash((start, end, k, feature_set))         # 特征集不同的缓存必须隔开
    if use_cache:
        with _LOCK:
            hit = _CACHE.get(key)
            if hit and time.time() < hit["exp"]:
                return hit["data"]

    feat = build_features(start, end, use_cache=use_cache).loc[:, cols].dropna()
    if len(feat) < max(3, k):
        return {"error": "样本量不足以聚类", "n_students": int(len(feat)), "k": k,
                "feature_set": feature_set}

    X = feat.to_numpy(float)
    scaler = StandardScaler()                           # 标准化：消除量纲差异（必须保留实例以便反变换）
    Xs = scaler.fit_transform(X)
    km = KMeans(n_clusters=k, n_init=10, random_state=42)   # 固定 random_state 保证可复现
    labels = km.fit_predict(Xs)

    # 轮廓系数评估聚类质量（样本多时随机抽 2000 个，否则 O(n^2) 太慢）
    sil = None
    if len(feat) >= 3 and 1 < k < len(feat):
        idx = np.arange(len(feat))
        if len(idx) > 2000:
            idx = np.random.default_rng(42).choice(idx, 2000, replace=False)
        try:
            sil = round(float(silhouette_score(Xs[idx], labels[idx])), 4)
        except ValueError:
            sil = None

    # 还原到原始量纲：cluster_centers_ 是标准化空间的坐标，直接展示会得到
    # "日均消费 0.06 元" 这类无意义数值，必须 inverse_transform 回真实单位；
    # 命名则改用等价的 z 分数（下面按群体均值/标准差换算，量纲无关）
    centers_raw = pd.DataFrame(scaler.inverse_transform(km.cluster_centers_), columns=feat.columns)
    # 除以标准差时先把 0 置换成 1：常量特征（整群行为一致）会造成除零
    std = np.where(X.std(0) == 0, 1.0, X.std(0))
    z = pd.DataFrame((centers_raw.to_numpy() - X.mean(0)) / std, columns=feat.columns)
    names = _name_clusters(z, rules)

    pca = PCA(n_components=2, random_state=42)          # 降维只用于画散点图，不参与聚类
    coords = pca.fit_transform(Xs)
    # 百分位排名（0-100）：个体画像页的雷达图需要把不同量纲的特征拉到同一尺度，
    # 用群体内分位数做映射比 min-max 更稳健（不受极端值拉伸）
    ranks = (feat.rank(pct=True) * 100).round(1)

    df_info = pd.read_sql(text(
        "SELECT student_id, name, college, major, class_name, gender FROM student"),
        con=db.engine).set_index("student_id")

    clusters = []
    for ci in range(k):
        mask = labels == ci
        members = feat.index[mask]
        # 簇中心均值就是论文里的"各类群体特征均值表"（已还原到真实量纲）
        stat = {fk: round(float(centers_raw.loc[ci, fk]), 2) for fk in cols}
        clusters.append({
            "cluster": int(ci),
            "label": names[ci],
            # desc 由本簇 z 分数自动生成（与 features 均值表同源，不会文数不符）；
            # definition 是命名规则里的通用画像解释，供论文正文引用
            "desc": describe_cluster(z.loc[ci]),
            "definition": rule_desc(names[ci], rules),
            "size": int(mask.sum()),
            "pct": round(float(mask.sum()) / len(feat) * 100, 2),
            "features": stat,
            "z_scores": {fk: round(float(z.loc[ci, fk]), 2) for fk in cols},
            "top_students": [
                {
                    "student_id": str(s),
                    "name": df_info.loc[s, "name"] if s in df_info.index else None,
                    "college": df_info.loc[s, "college"] if s in df_info.index else None,
                    "avg_daily_amount": round(float(feat.loc[s, "avg_daily_amount"]), 2),
                    "avg_daily_study_minutes": round(float(feat.loc[s, "avg_daily_study_minutes"]), 1),
                } for s in members[:8]
            ],
        })

    # 逐学生归类表：学号 + 各特征值 + 簇编号 + 簇标签（论文附表/导出 CSV 的同一数据源）
    points = [{
        "student_id": str(s),
        "cluster": int(l),
        "label": names[l],
        "x": round(float(p[0]), 3),
        "y": round(float(p[1]), 3),
        "name": df_info.loc[s, "name"] if s in df_info.index else None,
        "college": df_info.loc[s, "college"] if s in df_info.index else None,
        "features": {fk: round(float(feat.loc[s, fk]), 2) for fk in cols},
        "percentiles": {fk: float(ranks.loc[s, fk]) for fk in cols},
    } for s, l, p in zip(feat.index, labels, coords)]

    data = {
        "k": k,
        "feature_set": feature_set,
        "feature_keys": cols,
        "n_students": int(len(feat)),
        "date_start": start,
        "date_end": end,
        "inertia": round(float(km.inertia_), 2),
        "sse": round(float(km.inertia_), 2),        # 论文口径：SSE（簇内误差平方和）= inertia
        "silhouette": sil,                       # 越接近 1 越好；<0.25 说明簇分得不好
        "pca_explained": round(float(sum(pca.explained_variance_ratio_)), 4),
        "features": {fk: FEATURES[fk] for fk in cols},
        "group_mean": {fk: round(float(feat[fk].mean()), 2) for fk in cols},   # 做"簇 vs 全校"对比表用
        "clusters": clusters,
        "points": points,
        "cached_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if use_cache:
        with _LOCK:
            _CACHE[key] = {"data": data, "exp": time.time() + ttl}
            if len(_CACHE) > 32:                 # 防止不同参数组合把缓存撑爆
                oldest = min(_CACHE, key=lambda x: _CACHE[x]["exp"])
                _CACHE.pop(oldest, None)
    return data


def feature_of_student(student_id: str, start: str, end: str, k: int = 4,
                       feature_set: str = DEFAULT_FEATURE_SET) -> Optional[Dict[str, Any]]:
    """从缓存的聚类结果里取某个学生的特征与所属簇（个体画像页复用，避免重复算）"""
    res = fit_kmeans(start, end, k, feature_set=feature_set)
    if res.get("error"):
        return None
    for p in res["points"]:
        if p["student_id"] == student_id:
            # 连同簇说明一起返回，画像页才能写"你属于XX型：该簇日均在馆时长偏高 1.4σ"
            meta = next((c for c in res["clusters"] if c["cluster"] == p["cluster"]), {})
            return {**p, "label": meta.get("label", ""),
                    "desc": meta.get("desc", ""), "definition": meta.get("definition", ""),
                    "cluster_features": meta.get("features", {}),
                    "k": res["k"], "feature_set": res["feature_set"],
                    "date_start": start, "date_end": end}
    return None


def group_summary(start: str, end: str, feature_set: str = DEFAULT_FEATURE_SET) -> Dict[str, Any]:
    """群体各特征均值/中位数，个体画像页用来做"vs 全校平均"对比"""
    cols = FEATURE_SETS[normalize_feature_set(feature_set)]
    feat = build_features(start, end).loc[:, cols]
    return {
        "feature_set": normalize_feature_set(feature_set),
        "mean": {fk: round(float(feat[fk].mean()), 2) for fk in cols},
        "median": {fk: round(float(feat[fk].median()), 2) for fk in cols},
        "n_students": int(len(feat)),
    }


def elbow_curve(start: str, end: str, k_max: int = 8, k_min: int = 2,
                feature_set: str = DEFAULT_FEATURE_SET) -> Dict[str, Any]:
    """
    手肘法选 K：论文"K 值确定"一节的直接证据。
    返回 SSE(inertia) 曲线与轮廓系数曲线；默认 k 从 2 扫到 8（按总纲要求），
    k_min=1 时可取到 SSE 基准点（K=1 时 SSE 即总离差平方和，没有下降可误读）。
    """
    feature_set = normalize_feature_set(feature_set)
    cols = FEATURE_SETS[feature_set]
    k_min = max(1, min(int(k_min), 8))
    k_max = max(k_min, min(int(k_max), 12))
    feat = build_features(start, end).loc[:, cols].dropna()
    Xs = StandardScaler().fit_transform(feat.to_numpy(float))
    out = {"k": [], "inertia": [], "sse": [], "silhouette": []}
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xs)
        out["k"].append(k)
        out["inertia"].append(round(float(km.inertia_), 2))
        out["sse"].append(round(float(km.inertia_), 2))      # 与 inertia 同值，只是论文图表用 SSE 这个名字
        if k > 1:
            idx = np.arange(len(Xs))
            if len(idx) > 2000:
                idx = np.random.default_rng(42).choice(idx, 2000, replace=False)
            out["silhouette"].append(round(float(silhouette_score(Xs[idx], km.labels_[idx])), 4))
        else:
            out["silhouette"].append(None)
    out["n_students"] = int(len(feat))
    out["feature_set"] = feature_set
    out["feature_keys"] = cols
    # 样本方差总量：SSE 首点与之比就是"解释掉多少变异"，论文里能直接写降幅百分比
    out["total_ss"] = round(float(((Xs - Xs.mean(0)) ** 2).sum()), 2)
    return out
