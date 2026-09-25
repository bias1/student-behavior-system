# -*- coding: utf-8 -*-
"""
数据质量校验：确认模拟数据已按预期规律写入 MySQL，并量化"待清洗"脏数据。
是数据存储模块（清洗前置体检）与论文"数据合理性验证"章节的证据来源。

    python verify_data.py
"""

from __future__ import annotations

import os

import pymysql

from db_env import load_dotenv

load_dotenv()          # 与后端读同一份 .env，避免两处口令不一致

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", "123456"),
          database=os.getenv("DB_NAME", "student_behavior"), charset="utf8mb4")

CHECKS = [
    # (标题, SQL, 断言函数：返回 True 表示通过)
    ("各表行数", "SELECT (SELECT COUNT(*) FROM student) s,"
     "(SELECT COUNT(*) FROM consumption) c,(SELECT COUNT(*) FROM library_record) l,"
     "(SELECT COUNT(*) FROM warning) w", lambda r: r[0]["s"] > 0 and r[0]["c"] > 0),

    ("有效/无效消费记录", "SELECT is_valid, COUNT(*) n, ROUND(AVG(amount),2) avg_amt"
     " FROM consumption GROUP BY is_valid", lambda r: len(r) >= 1),

    ("生成列 meal_period 自动生效", "SELECT meal_period, COUNT(*) n FROM consumption"
     " WHERE is_valid=1 GROUP BY meal_period ORDER BY n DESC", lambda r: all(x["meal_period"] for x in r)),

    ("生成列 stay_minutes 自动生效", "SELECT COUNT(*) n, MIN(stay_minutes) mn, AVG(stay_minutes) av,"
     " MAX(stay_minutes) mx FROM library_record WHERE is_valid=1 AND stay_minutes IS NOT NULL",
     lambda r: r[0]["mn"] >= 0),

    ("三餐时间峰值（应集中在 8/12/18 点）", "SELECT HOUR(consumed_at) h, COUNT(*) n FROM consumption"
     " WHERE is_valid=1 GROUP BY h ORDER BY n DESC LIMIT 5", lambda r: len(r) == 5),

    ("工作日 vs 周末人均笔数", "SELECT WEEKDAY(consumed_at)>=5 is_we, COUNT(*) n,"
     " COUNT(DISTINCT DATE(consumed_at)) d, COUNT(DISTINCT student_id) s"
     " FROM consumption WHERE is_valid=1 GROUP BY is_we", lambda r: len(r) == 2),

    ("图书馆进馆时段双高峰", "SELECT HOUR(gate_in_time) h, COUNT(*) n FROM library_record"
     " WHERE is_valid=1 GROUP BY h ORDER BY n DESC LIMIT 6", lambda r: len(r) == 6),

    ("脏数据：金额为负/为零", "SELECT COUNT(*) n FROM consumption WHERE amount<=0 AND is_valid=0",
     lambda r: True),

    ("脏数据：离馆早于入馆", "SELECT COUNT(*) n FROM library_record"
     " WHERE gate_out_time IS NOT NULL AND gate_out_time<=gate_in_time", lambda r: True),

    ("脏数据：完全重复流水", "SELECT COUNT(*) n FROM (SELECT student_id, consumed_at, amount,"
     " COUNT(*) c FROM consumption GROUP BY 1,2,3 HAVING c>1) t", lambda r: True),

    ("孤儿学号（上游脏数据，需左连接识别）", "SELECT COUNT(*) n FROM consumption c"
     " LEFT JOIN student s ON s.student_id=c.student_id WHERE s.student_id IS NULL", lambda r: True),

    ("异常样本：单日消费 Top5（HIGH_CONSUME 应可识别）", "SELECT student_id, DATE(consumed_at) d,"
     " ROUND(SUM(amount),2) total FROM consumption WHERE is_valid=1"
     " GROUP BY student_id, d ORDER BY total DESC LIMIT 5", lambda r: r[0]["total"] > 300),

    ("异常样本：深夜消费 Top5（NIGHT_CONSUME 应可识别）", "SELECT student_id, COUNT(*) n"
     " FROM consumption WHERE is_valid=1 AND (HOUR(consumed_at)>=23 OR HOUR(consumed_at)<5)"
     " GROUP BY student_id ORDER BY n DESC LIMIT 5", lambda r: True),

    # 基准日动态取全库最后进馆日：旧实现写死 '2026-05-30'，重新生成其它区间的数据后验证口径错位
    ("异常样本：长期不进馆学生（NO_LIBRARY 应可识别）", "SELECT s.student_id,"
     " MAX(DATE(l.gate_in_time)) last_in FROM student s LEFT JOIN library_record l"
     " ON l.student_id=s.student_id AND l.is_valid=1 GROUP BY s.student_id"
     " HAVING last_in IS NULL OR DATEDIFF("
     " (SELECT MAX(DATE(gate_in_time)) FROM library_record WHERE is_valid=1), last_in)>=15 LIMIT 5",
     lambda r: True),
]

EXPLAINS = [
    ("个体画像：按学号+时间段查流水",
     "EXPLAIN SELECT * FROM consumption WHERE student_id='202203007'"
     " AND consumed_at BETWEEN '2026-05-01' AND '2026-05-31'"),
    ("群体热力：按时间范围聚合",
     "EXPLAIN SELECT HOUR(consumed_at), COUNT(*) FROM consumption"
     " WHERE consumed_at>='2026-05-01' GROUP BY HOUR(consumed_at)"),
    ("预警列表：状态+级别+日期分页",
     "EXPLAIN SELECT * FROM warning WHERE status=0 AND warning_level>=2"
     " ORDER BY warning_date DESC LIMIT 20"),
]


def run() -> None:
    conn = pymysql.connect(**DB)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    line = "-" * 78
    print(f"\n{line}\n数据质量校验报告\n{line}")
    for title, sql, assert_fn in CHECKS:
        cur.execute(sql)
        rows = cur.fetchall()
        ok = "PASS" if assert_fn(rows) else "FAIL"
        brief = str(rows[0]) if len(rows) == 1 else \
            " | ".join(f"{k}={v}" for k, v in list(rows[0].items()))
        print(f"[{ok}] {title}")
        print(f"       {brief[:150]}")
        if len(rows) > 1:
            print(f"       共 {len(rows)} 行，示例：{str(rows[:3])[:150]}")

    print(f"\n{line}\n索引命中验证（EXPLAIN）\n{line}")
    for title, sql in EXPLAINS:
        cur.execute(sql)
        r = cur.fetchone()
        key = r.get("key") or "(未走索引)"
        print(f"[{'PASS' if r.get('key') else 'WARN'}] {title:<28}"
              f" type={r.get('type'):<6} possible_keys={r.get('possible_keys')} -> key={key}"
              f" rows={r.get('rows')}")
    cur.close()
    conn.close()
    print(line + "\n")


if __name__ == "__main__":
    run()
