# -*- coding: utf-8 -*-
"""
安全核心回归测试（阶段 1 生产化，全部不依赖数据库）：
- .env 加载器与优先级
- 启动安全自查 security_check（只告警）与 prod fail-fast validate_config（拒绝启动）
- 严格整数解析
- 口令哈希 pbkdf2
- 数据范围 Scope：SQL 下推、缓存 key、单行判定
- 统一认证守卫：匿名/伪造 Cookie 一律 401，白名单端点放行

会话签发/CSRF/RBAC 越权/数据范围/吊销等需要真实库的行为在 test_rbac_scope.py。
"""

import os

import pytest
from flask import Flask

import config
from security import Scope
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


# =============================================================================
# 2. 启动安全自查（只告警，不阻断）
# =============================================================================

def test_security_check_flags_insecure_defaults_in_prod():
    warns = config.security_check({
        "APP_ENV": "prod", "DB_PASSWORD": "123456", "DB_USER": "root",
        "SECRET_KEY": "student-behavior-dev", "CORS_ORIGINS": "*", "AUTH_ENABLED": True,
    })
    text = "\n".join(warns)
    assert "DB_PASSWORD" in text and "SECRET_KEY" in text and "CORS" in text
    assert "root" in text                               # root 数据库账号必须点名
    assert "生产模式禁止" in text                       # prod 下升级成强告警


def test_security_check_warns_when_auth_disabled():
    warns = config.security_check({
        "APP_ENV": "dev", "DB_PASSWORD": "strong", "DB_USER": "app", "SECRET_KEY": "random",
        "CORS_ORIGINS": "http://localhost:5173", "AUTH_ENABLED": False,
    })
    assert any("AUTH_ENABLED=0" in w for w in warns)     # 关认证必须持续提醒


def test_security_check_quiet_when_hardened():
    warns = config.security_check({
        "APP_ENV": "prod", "DB_PASSWORD": "s3cret", "DB_USER": "sb_app",
        "SECRET_KEY": "random...", "CORS_ORIGINS": "https://bi.example.edu",
        "AUTH_ENABLED": True,
    })
    assert warns == []


# =============================================================================
# 3. prod fail-fast：不安全配置必须直接拒绝启动（validate_config 抛异常）
# =============================================================================

_HARDENED = {
    "APP_ENV": "prod", "SECRET_KEY": "a-very-random-secret", "DB_PASSWORD": "s3cureP@ss",
    "DB_USER": "sb_reader", "AUTH_ENABLED": True, "DEBUG": False,
    "CORS_ORIGINS": "https://bi.example.edu", "API_ADMIN_TOKEN": "",
    "SESSION_COOKIE_SECURE": True,
}


def test_validate_config_passes_when_hardened():
    config.validate_config(dict(_HARDENED))             # 不抛异常即通过


def test_validate_config_ignores_non_prod():
    bad = dict(_HARDENED, APP_ENV="dev", DB_USER="root", DB_PASSWORD="123456",
               SECRET_KEY="student-behavior-dev", CORS_ORIGINS="*", API_ADMIN_TOKEN="x")
    config.validate_config(bad)                          # 非 prod 直接 return，绝不阻断本地演示


@pytest.mark.parametrize("key,value,frag", [
    ("SECRET_KEY", "student-behavior-dev", "SECRET_KEY"),
    ("SECRET_KEY", "", "SECRET_KEY"),
    ("DB_PASSWORD", "123456", "默认"),
    ("DB_PASSWORD", "", "默认"),
    ("DB_USER", "root", "root"),
    ("AUTH_ENABLED", False, "认证"),
    ("DEBUG", True, "调试"),
    ("CORS_ORIGINS", "*", "CORS"),
    ("API_ADMIN_TOKEN", "leftover-bypass", "API_ADMIN_TOKEN"),
    ("SESSION_COOKIE_SECURE", False, "Secure"),
])
def test_validate_config_rejects_each_insecure_prod_setting(key, value, frag):
    bad = dict(_HARDENED)
    bad[key] = value
    with pytest.raises(config.ProductionConfigError) as ei:
        config.validate_config(bad)
    assert frag in str(ei.value)


def test_validate_config_collects_all_errors():
    bad = {k: v for k, v in _HARDENED.items()}
    bad.update(SECRET_KEY="student-behavior-dev", DB_USER="root", DB_PASSWORD="123456",
               AUTH_ENABLED=False, DEBUG=True, CORS_ORIGINS="*", API_ADMIN_TOKEN="x",
               SESSION_COOKIE_SECURE=False)
    with pytest.raises(config.ProductionConfigError) as ei:
        config.validate_config(bad)
    msg = str(ei.value)
    # 多个硬红线应一次性全部列出，便于运维一次改到位
    assert msg.count("  - ") >= 7


# =============================================================================
# 4. 严格整数解析：非法值给 400 文案而不是抛 ValueError
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
# 5. 口令哈希：pbkdf2-sha256（纯函数层，不发请求）
# =============================================================================

def test_password_hash_roundtrip():
    from api.auth import make_password_hash, verify_password

    h = make_password_hash("s3cret", iterations=1_000)   # 测试用小迭代数，生产 20 万
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)
    assert not verify_password("s3cret", "")               # 空存储串必须判失败
    assert not verify_password("s3cret", "broken$format")  # 被改坏的哈希串不能放过
    # 加盐随机：同一口令两次哈希不同，但都能验证通过
    assert make_password_hash("s3cret", 1_000) != make_password_hash("s3cret", 1_000)


# =============================================================================
# 6. 数据范围 Scope：SQL 下推、缓存 key、单行判定（授权边界的地基）
# =============================================================================

def test_scope_all_is_unrestricted():
    s = Scope(all=True)
    assert s.all and not s.is_empty()
    assert s.key() == "*"
    frag, params = s.sql_filter(col="student_id")
    assert frag == "" and params == {}                    # 全校：不加任何过滤
    assert s.contains_student_row({"student_id": "x"})    # 任意学生都在范围内


def test_scope_empty_is_never_unrestricted():
    """空范围绝不能退化成'不过滤'——这是防越权看全校的关键。"""
    s = Scope()
    assert s.is_empty()
    assert s.key() == "empty"
    frag, params = s.sql_filter(col="student_id")
    assert "1=0" in frag and params == {}                 # 下推永假谓词
    assert not s.contains_student_row({"student_id": "x", "college": "any"})


def test_scope_college_pushdown_binds_params():
    s = Scope(colleges=frozenset({"计算机学院", "法政学院"}))
    frag, params = s.sql_filter(col="student_id")
    assert "college IN" in frag and "SELECT student_id FROM student" in frag
    assert set(params["scp_col"]) == {"计算机学院", "法政学院"}   # 授权值走绑定参数，不拼 SQL
    assert s.contains_student_row({"student_id": "1", "college": "法政学院"})
    assert not s.contains_student_row({"student_id": "1", "college": "外国语学院"})


def test_scope_grade_and_student_and_class():
    s = Scope(grades=frozenset({"2022"}), student_ids=frozenset({"S001"}),
              classes=frozenset({"计科2101"}))
    assert s.contains_student_row({"student_id": "S001", "college": "", "class_name": "", "grade_year": ""})
    assert s.contains_student_row({"student_id": "S999", "grade_year": "2022"})
    assert s.contains_student_row({"student_id": "S999", "class_name": "计科2101"})
    assert not s.contains_student_row({"student_id": "S999", "college": "X", "class_name": "Y", "grade_year": "2020"})
    # 授权值参与缓存 key：同窗口不同范围必须是不同指纹（防跨用户串缓存）
    assert Scope(colleges=frozenset({"A"})).key() != Scope(colleges=frozenset({"B"})).key()


# =============================================================================
# 7. 统一认证守卫（不依赖数据库）
# =============================================================================

def test_guard_blocks_anonymous_read(client):
    for path in ("/api/warning/list", "/api/overview", "/api/student/list",
                 "/api/consumption/trend", "/api/clustering/result"):
        assert client.get(path).status_code == 401, path


def test_guard_anonymous_post_is_401(client):
    # 未登录时先被 401 拦截（CSRF 的 403 只对已登录会话生效）
    assert client.post("/api/warning/scan", json={}).status_code == 401


def test_guard_whitelist_anonymous(client):
    r = client.get("/api/auth/status")                   # 登录入口不能要求先登录
    assert r.status_code == 200
    assert r.get_json()["data"]["enabled"] is True
    r = client.get("/api/health")                        # 探活匿名可用（信息已裁剪）
    assert r.status_code in (200, 500)                   # 无库时连接失败 500 属预期


def test_guard_rejects_forged_session_cookie(client):
    client.set_cookie("sb_session", "forged-token-not-in-db")
    assert client.get("/api/overview").status_code == 401


def test_legacy_offline_mode_grants_anonymous_read(app, client):
    # AUTH_ENABLED=0 仅供非 prod 离线演示：读匿名放行、视为全校范围
    app.config["AUTH_ENABLED"] = False
    r = client.get("/api/overview")
    assert r.status_code != 401                          # 放行进入业务层（无库则 500）
