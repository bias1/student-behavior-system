# -*- coding: utf-8 -*-
"""
pytest 共用配置。

- 纯逻辑/守卫用例：用 app/client fixture（create_app 只建对象，不要求数据库）。
- RBAC / 数据范围 / 会话吊销等集成用例：用 rbac fixture，它需要本地 MySQL 已跑
  Alembic 迁移（role/permission 种子就位）且有学生数据；否则自动 skip，不谎报通过。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试会话内不启动后台作业 worker：提交的异步作业保持 pending，状态机可确定性断言。
os.environ.setdefault("START_WORKER", "0")


@pytest.fixture
def app():
    """离线可构建的 dev app（不连库也不报错）；认证默认开启，Cookie 非 Secure 便于本地测试。"""
    from app import create_app

    application = create_app("dev")
    application.config.update(AUTH_ENABLED=True, SESSION_COOKIE_SECURE=False)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# =============================================================================
# 集成测试：需要数据库 + 已迁移的权限表 + 已种子的角色 + 真实学生样本
# =============================================================================

@pytest.fixture(scope="session")
def _db_app():
    from sqlalchemy import text

    from app import create_app
    from models import db

    application = create_app("dev")
    application.config.update(AUTH_ENABLED=True, SESSION_COOKIE_SECURE=False)
    try:
        with application.app_context():
            db.session.execute(text("SELECT code FROM role LIMIT 1"))          # 迁移+种子是否就位
            db.session.execute(text("SELECT college FROM student LIMIT 1"))    # 是否有学生数据
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"集成用例需要本地 MySQL（含 Alembic 迁移/种子与数据），跳过：{exc}")
    return application


class RbacHarness:
    """持有一次性测试用户与真实数据事实，按需产出"已登录"的 test_client。"""

    def __init__(self, application, users, facts):
        self.app = application
        self.users = users          # role -> (username, password)
        self.facts = facts          # dict: college_a/college_b/sid_a/sid_b

    def client_for(self, role):
        client = self.app.test_client()
        username, password = self.users[role]
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, f"{role} 登录失败：{r.status_code} {r.get_json()}"
        return client

    def csrf(self, client):
        ck = client.get_cookie("sb_csrf")
        return ck.value if ck else ""

    def anon_client(self):
        return self.app.test_client()


@pytest.fixture(scope="session")
def rbac(_db_app):
    """
    建三类最小权限测试用户（用完即删，不污染既有数据）：
      counselor_a：仅学院 A 数据范围，可看个体明细；
      analyst：全校范围，但无 student:detail（用于验 403 越权 + 聚类脱敏）；
      auditor：全校范围，只有 audit:read（用于验 403）。
    同时取真实学院/学号样本用于跨范围越权断言。
    """
    from sqlalchemy import text

    from api.auth import make_password_hash
    from models import (LoginSession, SystemUser, UserRole, UserStudentScope, db)

    app = _db_app
    facts = {}
    created_ids = []

    def _mk(username, roles, scope_type, scope_value):
        u = SystemUser(username=username,
                       password_hash=make_password_hash("Intg#2026", iterations=1_000),
                       display_name="集成测试", status=1)
        db.session.add(u)
        db.session.flush()
        created_ids.append(u.id)
        for rc in roles:
            db.session.add(UserRole(user_id=u.id, role_code=rc))
        db.session.add(UserStudentScope(user_id=u.id, scope_type=scope_type,
                                        scope_value=scope_value, granted_by="pytest"))
        return u

    with app.app_context():
        rows = db.session.execute(text(
            "SELECT college, COUNT(*) n FROM student GROUP BY college HAVING n >= 6 "
            "ORDER BY n DESC LIMIT 2")).all()
        if len(rows) < 2:
            pytest.skip("学生数据不足两个学院，无法验证跨学院越权，跳过集成用例")
        college_a, college_b = rows[0][0], rows[1][0]
        sid_a = db.session.execute(text(
            "SELECT student_id FROM student WHERE college=:c LIMIT 1"), {"c": college_a}).scalar()
        sid_b = db.session.execute(text(
            "SELECT student_id FROM student WHERE college=:c LIMIT 1"), {"c": college_b}).scalar()
        facts.update(college_a=college_a, college_b=college_b, sid_a=sid_a, sid_b=sid_b)

        u1 = _mk("it_counselor_a", ["counselor"], "college", college_a)
        u2 = _mk("it_analyst", ["analyst"], "*", "*")
        u3 = _mk("it_auditor", ["auditor"], "*", "*")
        db.session.commit()
        users = {
            "counselor_a": (u1.username, "Intg#2026"),
            "analyst": (u2.username, "Intg#2026"),
            "auditor": (u3.username, "Intg#2026"),
        }

    try:
        yield RbacHarness(app, users, facts)
    finally:
        with app.app_context():
            for uid in created_ids:
                LoginSession.query.filter_by(user_id=uid).delete(synchronize_session=False)
                u = db.session.get(SystemUser, uid)
                if u is not None:
                    db.session.delete(u)      # roles/scopes 由 ORM 级联删除
            db.session.commit()
