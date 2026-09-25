# -*- coding: utf-8 -*-
"""
安全加固项的回归测试（凭证外置 / 严格参数解析 / 登录守卫 / 口令哈希与 token）。
全部不依赖数据库：create_app 只建对象不连库；被放行的请求落到业务层后
可能因连不上库返回 500，所以守卫用例断言"不再是 401"而不是"等于 200"。
"""

import os

import pytest
from flask import Flask

import config
from utils import parse_int_strict


# =============================================================================
# 1. .env 加载器
# =============================================================================

def test_load_dotenv_parses_and_respects_priority(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# 注释行\nDB_PASSWORD=secret123\nSECRET_KEY='quoted key'\nBADLINE\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DB_PASSWORD", "from-process")   # 已有环境变量优先级最高，不许被覆盖
    loaded = config.load_dotenv(str(env_file))
    try:
        assert loaded == 1                              # 只有 SECRET_KEY 是新载入的
        assert os.environ["DB_PASSWORD"] == "from-process"
        assert os.environ["SECRET_KEY"] == "quoted key"  # 引号被剥掉、无 = 号的行被跳过
    finally:
        os.environ.pop("SECRET_KEY", None)
        # DB_PASSWORD 由 monkeypatch 管理，自动恢复


# =============================================================================
# 2. 启动安全自查（prod 判定看 APP_ENV，不再看 DEBUG；登录口令默认值是必查项）
# =============================================================================

def test_security_check_flags_insecure_defaults_in_prod():
    warns = config.security_check({
        "APP_ENV": "prod", "DB_PASSWORD": "123456", "SECRET_KEY": "student-behavior-dev",
        "CORS_ORIGINS": "*", "AUTH_ENABLED": True,
        "AUTH_PASSWORD": "admin123", "AUTH_PASSWORD_HASH": "",
    })
    text = "\n".join(warns)
    assert "DB_PASSWORD" in text and "SECRET_KEY" in text and "CORS" in text
    assert "admin123" in text                           # 默认登录口令必须被点名
    assert "生产模式禁止" in text                       # prod 下升级成强告警


def test_security_check_warns_plaintext_password_and_disabled_auth():
    warns = config.security_check({
        "APP_ENV": "dev", "DB_PASSWORD": "strong", "SECRET_KEY": "random",
        "CORS_ORIGINS": "http://localhost:5173", "AUTH_ENABLED": True,
        "AUTH_PASSWORD": "MyStr0ng!", "AUTH_PASSWORD_HASH": "",
    })
    assert any("AUTH_PASSWORD_HASH" in w for w in warns)   # 明文口令建议换哈希
    warns = config.security_check({
        "APP_ENV": "dev", "DB_PASSWORD": "strong", "SECRET_KEY": "random",
        "CORS_ORIGINS": "http://localhost:5173", "AUTH_ENABLED": False,
    })
    assert any("AUTH_ENABLED=0" in w for w in warns)       # 关认证必须持续提醒


def test_security_check_quiet_when_hardened():
    warns = config.security_check({
        "APP_ENV": "prod", "DB_PASSWORD": "s3cret", "SECRET_KEY": "random...",
        "CORS_ORIGINS": "http://localhost:5173", "AUTH_ENABLED": True,
        "AUTH_PASSWORD": "", "AUTH_PASSWORD_HASH": "pbkdf2:sha256:200000$x$y",
    })
    assert warns == []


# =============================================================================
# 3. 严格整数解析：非法值给 400 文案而不是抛 ValueError
# =============================================================================

_APP = Flask(__name__)


def test_parse_int_strict_cases():
    with _APP.test_request_context("/x"):
        assert parse_int_strict("status") == (None, None)          # 没传
    with _APP.test_request_context("/x?status=1"):
        assert parse_int_strict("status", allowed=(0, 1, 2)) == (1, None)
    with _APP.test_request_context("/x?status=abc"):
        v, err = parse_int_strict("status", allowed=(0, 1, 2))
        assert v is None and "必须是整数" in err
    with _APP.test_request_context("/x?status=9"):
        v, err = parse_int_strict("status", allowed=(0, 1, 2))
        assert v is None and "只能是" in err
    with _APP.test_request_context("/x?level=0"):
        v, err = parse_int_strict("level", bounds=(1, 3))
        assert v is None and "范围" in err


# =============================================================================
# 4. 口令哈希与 token 签发/校验（纯函数层，不发请求）
# =============================================================================

def test_password_hash_roundtrip():
    from api.auth import make_password_hash, verify_password

    h = make_password_hash("s3cret", iterations=1_000)   # 测试用小迭代数，生产 20 万
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)
    assert not verify_password("s3cret", "")               # 空存储串必须判失败
    assert not verify_password("s3cret", "broken$format")  # 被改坏的哈希串不能放过


def test_token_sign_and_verify(app):
    from api.auth import issue_token, parse_token

    with app.app_context():
        token, ttl = issue_token("admin")
        assert ttl > 0
        data = parse_token(token)
        assert data and data["u"] == "admin" and data["role"] == "admin"
        assert parse_token("not-a-token") is None
        assert parse_token("") is None


def test_token_expired(app, monkeypatch):
    from api.auth import issue_token, parse_token

    with app.app_context():
        monkeypatch.setitem(app.config, "AUTH_TOKEN_TTL", -10)   # 签发即过期
        token, _ = issue_token("admin")
        assert parse_token(token) is None


# =============================================================================
# 5. 登录守卫（app fixture 见 conftest.py：AUTH_* 已钉死为本测试专用配置）
# =============================================================================

def test_guard_blocks_anonymous_read(client):
    r = client.get("/api/warning/list")
    assert r.status_code == 401
    r = client.get("/api/overview")
    assert r.status_code == 401
    r = client.get("/api/student/list")
    assert r.status_code == 401


def test_guard_whitelist_anonymous(client):
    r = client.get("/api/auth/status")                  # 登录入口不能要求先登录
    assert r.status_code == 200
    assert r.get_json()["data"]["enabled"] is True
    r = client.get("/api/health")                       # 探活匿名可用（信息已被裁剪，见 app.py）
    assert r.status_code in (200, 500)                 # 无库时 500 是连接失败，合理


def test_login_and_token_access(client):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "test-password"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["token"] and data["username"] == "admin"
    headers = {"Authorization": f"Bearer {data['token']}"}
    r = client.get("/api/auth/me", headers=headers)     # 身份回显
    assert r.status_code == 200 and r.get_json()["data"]["username"] == "admin"
    r = client.get("/api/warning/list", headers=headers)
    # token 正确 -> 放行进入业务逻辑（无数据库时会是 500，但绝不能是 401）
    assert r.status_code != 401


@pytest.mark.parametrize("bad", [
    {"username": "admin", "password": "wrong"},
    {"username": "hack3r", "password": "test-password"},
    {"username": "", "password": ""},                   # .env 空值攻击面：必须 401 不是放行
])
def test_login_rejected(client, bad):
    r = client.post("/api/auth/login", json=bad)
    assert r.status_code == 401


def test_forged_token_rejected(client):
    r = client.get("/api/overview", headers={"Authorization": "Bearer forged.token.value"})
    assert r.status_code == 401


def test_login_uses_password_hash(app, client):
    from api.auth import make_password_hash

    app.config["AUTH_PASSWORD_HASH"] = make_password_hash("hashed-pw", iterations=1_000)
    r = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"})
    assert r.status_code == 401                         # 配了哈希后明文凭据失效
    r = client.post("/api/auth/login", json={"username": "admin", "password": "hashed-pw"})
    assert r.status_code == 200


def test_admin_token_bypass(client):
    # app fixture 已配 API_ADMIN_TOKEN：服务级旁路，脚本免登录可读写
    r = client.get("/api/overview", headers={"X-API-Token": "smoke-bypass"})
    assert r.status_code != 401
    r = client.post("/api/warning/scan", headers={"X-API-Token": "wrong-token"})
    assert r.status_code == 401


def test_guard_legacy_mode_when_auth_disabled(app, client):
    app.config["AUTH_ENABLED"] = False                  # 旧语义：读匿名放行、写要 token
    assert client.get("/api/warning/list").status_code != 401
    assert client.post("/api/warning/scan").status_code == 401
    r = client.post("/api/warning/scan", headers={"X-API-Token": "smoke-bypass"})
    assert r.status_code != 401
