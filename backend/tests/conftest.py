# -*- coding: utf-8 -*-
"""pytest 共用配置：backend 目录挂进 sys.path + 守卫测试用的无库 Flask 应用 fixture。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """不连数据库的 app（create_app 只建对象）；AUTH_* 钉死为本测试专用配置，
    不受本地 .env 影响；API_ADMIN_TOKEN 也预设，旁路类用例直接用，
    需要改动的用例在测试体内覆盖 app.config 即可。"""
    from app import create_app

    application = create_app("dev")
    application.config.update(
        AUTH_ENABLED=True,
        AUTH_USERNAME="admin",
        AUTH_PASSWORD="test-password",
        AUTH_PASSWORD_HASH="",
        AUTH_TOKEN_TTL=3600,
        API_ADMIN_TOKEN="smoke-bypass",
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
