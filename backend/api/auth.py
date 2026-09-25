# -*- coding: utf-8 -*-
"""
认证接口（轻量登录守卫，非完整 RBAC）
  GET  /api/auth/status  登录开关探测（匿名可访问，前端路由守卫决定要不要跳登录页）
  POST /api/auth/login   {username,password} -> {token, expires_in, username}
  GET  /api/auth/me      校验 token 并回显身份（前端刷新页面时恢复登录态）

设计约定（刻意控制复杂度，理由见 README"安全设计说明"）：
- 单管理员账号，凭证只来自环境变量/.env：AUTH_USERNAME + AUTH_PASSWORD_HASH（推荐，
  pbkdf2 哈希）；未配哈希时回退 AUTH_PASSWORD（默认 admin/admin123，仅限本地演示，
  security_check 会持续告警）。AUTH_ENABLED=0 可整体关闭（纯离线演示）。
- token 用 itsdangerous 对 SECRET_KEY 签名（内含过期时间戳），无状态、不引第三方 JWT 库。
- 校验统一在 app.py 的 _auth_guard（before_request）：除白名单外所有 /api/* 必须携带
  Authorization: Bearer <token>；API_ADMIN_TOKEN 作为脚本/定时任务的旁路凭证继续有效。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional, Tuple

from flask import Blueprint, current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from utils import fail, ok

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_ITERATIONS = 200_000


# =============================================================================
# 口令哈希：pbkdf2-sha256（Python 标准库自带，避免为毕设引入 bcrypt 编译依赖）
# 存储格式  pbkdf2:sha256:<iterations>$<salt_hex>$<hash_hex>
# =============================================================================

def make_password_hash(password: str, iterations: int = _ITERATIONS) -> str:
    """生成可直接写进 .env AUTH_PASSWORD_HASH 的口令哈希（README 有使用说明）"""
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2:sha256:{iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, hexhash = stored.split("$")
        iterations = int(scheme.rsplit(":", 1)[-1])
    except ValueError:
        return False                       # 存储串被改坏时宁可判失败，不能让所有人空密码登入
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(dk.hex(), hexhash)


# =============================================================================
# token 签发 / 校验（itsdangerous 时间戳签名，过期由服务端 max_age 兜底）
# =============================================================================

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="api-auth")


def issue_token(username: str) -> Tuple[str, int]:
    ttl = int(current_app.config.get("AUTH_TOKEN_TTL", 43200))
    token = _serializer().dumps({"u": username, "role": "admin", "exp": int(time.time()) + ttl})
    return token, ttl


def parse_token(token: str) -> Optional[dict]:
    """合法返回负载 dict，非法/过期返回 None（不区分原因，避免给探测者信息）"""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=int(current_app.config.get("AUTH_TOKEN_TTL", 43200)))
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) and data.get("u") else None


# =============================================================================
# 接口
# =============================================================================

@bp.get("/status")
def auth_status():
    """前端路由守卫先问一次：没开认证就不该把用户挡在登录页外面"""
    return ok({"enabled": bool(current_app.config.get("AUTH_ENABLED"))})


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    cfg = current_app.config
    # 服务端凭证配置为空时直接拒绝（防止错误配置出"空密码 admin"账号）；
    # 正常路径由 config 的 `or` 回退保证非空，这里是第二道防线
    expected_user = str(cfg.get("AUTH_USERNAME") or "")
    if not expected_user or (not cfg.get("AUTH_PASSWORD_HASH") and not cfg.get("AUTH_PASSWORD")):
        current_app.logger.error("[登录配置] AUTH_USERNAME/AUTH_PASSWORD 未配置，拒绝所有登录")
        return fail("服务端登录账号未配置，请联系管理员检查 .env", 500)
    # 用户名与口令都走定长比较，不通过响应时间暴露"用户名是否存在"
    user_ok = hmac.compare_digest(username, expected_user)
    stored_hash = cfg.get("AUTH_PASSWORD_HASH") or ""
    if stored_hash:
        pwd_ok = verify_password(password, stored_hash)
    else:
        pwd_ok = hmac.compare_digest(password, str(cfg.get("AUTH_PASSWORD") or ""))
    if not (user_ok and pwd_ok):
        current_app.logger.warning("[登录失败] username=%s ip=%s", username[:40], request.remote_addr)
        return fail("用户名或密码错误", 401)          # 不区分"用户错/密码错"
    token, ttl = issue_token(username)
    return ok({"token": token, "expires_in": ttl, "username": username, "role": "admin"})


@bp.get("/me")
def me():
    """守卫已验过 token（本路径不在匿名白名单里），这里只做身份回显"""
    auth = request.headers.get("Authorization", "")
    data = parse_token(auth[7:] if auth.startswith("Bearer ") else "")
    if not data:
        return fail("未登录或登录已过期", 401)
    return ok({"username": data["u"], "role": data.get("role"), "expires_at": data.get("exp")})
