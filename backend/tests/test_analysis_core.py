# -*- coding: utf-8 -*-
"""
分析层核心逻辑单测（P2：优先覆盖纯计算、易出回归的函数，不依赖数据库）

重点是安全清单里点名的两处算法缺陷：
1. 自然周对齐的跨年边界（12 月底 ~ 1 月初）——_complete_weeks / _week_start；
2. 簇命名的贪心指派与"关键特征显著性门槛"——_name_clusters。
这些逻辑一旦改坏，大屏与预警会静默出错，必须有测试兜住。
"""

import numpy as np
import pandas as pd

from analysis import clustering, warning
from analysis.warning_rules import _night_hours


# =============================================================================
# 1. 自然周对齐：跨年边界是清单点名的坑，重点覆盖
# =============================================================================

def test_week_start_maps_every_day_to_monday():
    """一周任意一天都应映射到所在周的周一（含周日，中国口径周日是一周之末）"""
    # 2026-01-01 是周四，所在自然周的周一是 2025-12-29（跨年！）
    s = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-04", "2025-12-29", "2025-12-31"]))
    ws = warning._week_start(s)
    assert (ws == pd.Timestamp("2025-12-29")).all(), "跨年周应统一归到 2025-12-29 这个周一"


def test_complete_weeks_across_year_boundary():
    """
    跨年窗口 2025-12-29 ~ 2026-01-11：两个自然周都完整覆盖，
    若把年边界当成周边界，这里只会剩一个周甚至清零，导致 CONSUME_DROP 整段漏算。
    """
    weeks = warning._complete_weeks("2025-12-29", "2026-01-11")
    assert [str(w.date()) for w in weeks] == ["2025-12-29", "2026-01-05"]


def test_complete_weeks_drops_partial_edges():
    """
    窗口首日/末日所在的残缺周必须丢弃：2026-01-02（周五）起，第一周不完整，
    应从下一个完整周 2025-12-29… 不对，12-29 那周在窗口外，故首个完整周是 2026-01-05。
    残缺周参与环比会造成"3 天 vs 7 天"的假骤降。
    """
    # 2026-01-02(五) ~ 2026-01-18(日)：12-29 周在窗口外，01-05、01-12 两周完整
    weeks = warning._complete_weeks("2026-01-02", "2026-01-18")
    assert [str(w.date()) for w in weeks] == ["2026-01-05", "2026-01-12"]


def test_complete_weeks_empty_when_no_full_week():
    """不足 7 天的窗口没有任何完整周，返回空列表（规则此时应直接跳过而非误报）"""
    assert warning._complete_weeks("2026-01-05", "2026-01-09") == []


def test_streak_counts_consecutive_days():
    """_streak：连续 True 的天数逐日累计，断档归零（W1/W3 连续型规则的地基）"""
    flag = pd.DataFrame(
        [[True, True, False, True, True, True]],
        index=pd.Index(["S1"], name="student_id"),
        columns=pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04",
                                "2026-03-05", "2026-03-06", "2026-03-07"]),
    )
    out = warning._streak(flag).to_numpy()
    assert out.tolist() == [[1, 2, 0, 1, 2, 3]]


# =============================================================================
# 2. 簇命名：贪心指派 + 关键特征显著性门槛
# =============================================================================

def test_name_clusters_respects_key_significance_threshold():
    """
    关键特征 z 分数未达 KEY_MIN_Z 时不得硬贴画像标签，应回落到"群体N"。
    这是防止"数据几乎没差别却命名成不规律型"答辩翻车的那道门槛。
    """
    cols = clustering.FEATURE_SETS["core"]
    # 所有特征都贴近均值（z≈0），没有任何一条规则的关键特征够格
    centers_z = pd.DataFrame(np.zeros((1, len(cols))), columns=cols)
    names = clustering._name_clusters(centers_z, clustering.rules_for("core"))
    assert names == ["群体1"], "全零 z 分数不应命中任何画像规则"


def test_name_clusters_assigns_distinct_labels_no_duplicate():
    """两条规则可命中时应贪心指派为不同标签，绝不把同一画像名重复分给两个簇。"""
    cols = clustering.FEATURE_SETS["core"]
    z = pd.DataFrame(np.zeros((2, len(cols))), columns=cols)
    # 簇0：图书馆时长极高（重度用户）；簇1：消费时间标准差极高（不规律型）
    z.loc[0, "avg_daily_study_minutes"] = 3.0
    z.loc[1, "meal_time_std"] = 3.0
    names = clustering._name_clusters(z, clustering.rules_for("core"))
    assert len(names) == 2
    assert len(set(names)) == 2, "两个簇不应拿到同一标签（贪心指派保证不重复）"


def test_name_clusters_terminates_when_rules_exceed_clusters():
    """簇数少于可用规则数时贪心循环必须正常终止（历史上这里死循环卡死过接口）。"""
    cols = clustering.FEATURE_SETS["full"]
    z = pd.DataFrame(np.random.default_rng(0).normal(size=(2, len(cols))), columns=cols)
    names = clustering._name_clusters(z, clustering.rules_for("full"))
    assert len(names) == 2 and all(names)


def test_normalize_feature_set_rejects_unknown():
    """非法特征集参数必须回落默认，绝不能把外部字符串当列名用。"""
    assert clustering.normalize_feature_set("core") == "core"
    assert clustering.normalize_feature_set("'; DROP TABLE") == clustering.DEFAULT_FEATURE_SET
    assert clustering.normalize_feature_set(None) == clustering.DEFAULT_FEATURE_SET


# =============================================================================
# 3. 夜间时段配置解析：非法值兜底，不让规则因配置写错而崩
# =============================================================================

def test_night_hours_parses_config_and_clamps():
    assert _night_hours({"json": {"start": "23:00", "end": "05:00"}}) == (23, 5)
    # 越界与非法值都应被夹到合法小时区间或退回默认
    assert _night_hours({"json": {"start": "99:00"}}) == (23, 5)
    assert _night_hours({}) == (23, 5)
