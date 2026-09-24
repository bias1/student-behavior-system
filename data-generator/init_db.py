# -*- coding: utf-8 -*-
"""
一键初始化数据库：执行 database/schema.sql 建库建表 + 灌入预警规则。
避免依赖 mysql 命令行客户端（Windows 下 PowerShell 不支持 < 重定向，
且管道传中文会破坏 UTF-8 编码）。

    python init_db.py                       # 默认读 ../database/schema.sql
    python init_db.py --sql ../database/schema.sql
"""

from __future__ import annotations

import argparse
import os
import sys

import pymysql

DEFAULT_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "database", "schema.sql")


def split_statements(text: str) -> list[str]:
    """
    按"行尾分号"切分语句。schema.sql 中所有语句都以分号结尾且无存储过程，
    因此无需处理 DELIMITER；同时跳过 -- 行注释与空行。
    """
    stmts, buf = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        if s.endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                stmts.append(stmt.rstrip(";"))
            buf = []
    if buf and "\n".join(buf).strip():
        stmts.append("\n".join(buf).strip())
    return stmts


def main() -> int:
    ap = argparse.ArgumentParser(description="初始化 MySQL 数据库")
    ap.add_argument("--sql", default=os.path.normpath(DEFAULT_SQL))
    ap.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("DB_USER", "root"))
    ap.add_argument("--password", default=os.getenv("DB_PASSWORD", "123456"))
    a = ap.parse_args()

    with open(a.sql, encoding="utf-8") as f:
        stmts = split_statements(f.read())
    conn = pymysql.connect(host=a.host, port=a.port, user=a.user,
                           password=a.password, charset="utf8mb4", autocommit=True)
    with conn.cursor() as cur:
        for i, stmt in enumerate(stmts, 1):
            try:
                cur.execute(stmt)
            except Exception as exc:                              # noqa: BLE001
                print(f"[fail] 第 {i} 条语句执行失败：{exc}\n{stmt[:120]} ...", file=sys.stderr)
                return 1
    db = os.getenv("DB_NAME", "student_behavior")
    with conn.cursor() as cur:
        cur.execute("USE " + db)
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM warning_rule")
        n_rule = cur.fetchone()[0]
    conn.close()
    print(f"[ok ] 已执行 {len(stmts)} 条语句 | 数据库 {db} | 表 {tables} | 预警规则 {n_rule} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
