# -*- coding: utf-8 -*-
"""
认证接口（阶段 1 生产化：httpOnly Cookie 会话 + CSRF + 登录限流 + 可吊销）

  GET  /api/auth/status  登录开关探测（匿名可访问，前端路由守卫决定要不要跳登录页）
  POST /api/auth/login   {username,password} -> 下发会话 Cookie，回显身份/权限/范围
  POST /api/auth/logout  吊销当前会话并清 Cookie
  GET  /api/auth/me      依据会话 Cookie 回显当前身份（前端刷新页面恢复登录态）

设计约定：
- 用户主体是数据库 system_user 表（不再是环境变量里的单管理员）。口令只存
  pbkdf2-sha256 哈希（沿用下方 make_password_hash/verify_password，标准库实现）。
- 会话由 security.start_session 签发：Cookie 里放随机令牌，库里只存 sha256(令牌)，
  每次请求实时查 LoginSession —— 退出/禁用/改密/管理员踢出均即时生效（可吊销）。
- CSRF 采用双提交令牌：登录时下发可读 Cookie(sb_csrf) 并存库，非 GET 请求须带
  X-CSRF-Token 头且与库中值一致（校验在 app.py 守卫里统一做）。
- 登录失败限流：连续失败达 LOGIN_MAX_FAILURES 锁定 LOGIN_LOCKOUT_SECONDS 秒，
  计数与锁定截止落库，多进程/重启后依然生效。
- 日志/审计绝不记录明文口令与完整令牌。
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, current_app, g, request

from models import SystemUser, db
from security import (apply_session_cookies, audit, clear_session_cookies, current_user,
                      resolve_scope, start_session)
from utils import fail, ok

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_ITERATIONS = 200_000


# =============================================================================
# 口令哈希：pbkdf2-sha256（Python 标准库，避免引入 bcrypt 编译依赖）
# 存储格式  pbkdf2:sha256:<iterations>$<salt_hex>$<hash_hex>
# =============================================================================

def make_password_hash(password: str, iterations: int = _ITERATIONS) -> str:
    """生成写进 system_user.password_hash 的口令哈希（CLI/迁移建用户时调用）"""
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2:sha256:{iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, hexhash = stored.split("$")
        iterations = int(scheme.rsplit(":", 1)[-1])
    except ValueError:
        return False                       # 存储串被改坏时宁可判失败，不能让空密码登入
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(dk.hex(), hexhash)


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
    username = str(payload.get("username") or "")[:64]
    password = str(payload.get("password") or "")
    cfg = current_app.config

    user = SystemUser.query.filter_by(username=username).first()
    now = datetime.now()

    # 账号不存在：不回滚式枚举——仍走一次口令哈希比对，让响应时间与"存在但口令错"一致
    if user is None:
        verify_password(password, make_password_hash("dummy-compare-timing"))
        audit("login_fail", target=f"user:{username[:40]}", detail={"reason": "no_such_user"},
              result="denied")
        return fail("用户名或密码错误", 401)

    # 锁定中：直接拒绝，不做口令比对（也不泄露是否命中密码）
    if user.locked_until and user.locked_until > now:
        remain = int((user.locked_until - now).total_seconds())
        audit("login_fail", target=f"user:{user.id}", detail={"reason": "locked"}, result="denied")
        return fail(f"账号已锁定，请 {remain} 秒后重试或联系管理员", 429)

    if int(user.status) != 1:
        audit("login_fail", target=f"user:{user.id}", detail={"reason": "disabled"}, result="denied")
        return fail("账号已禁用，请联系管理员", 403)

    if not verify_password(password, user.password_hash or ""):
        user.failed_attempts = int(user.failed_attempts or 0) + 1
        maxf = int(cfg.get("LOGIN_MAX_FAILURES", 5))
        locked = False
        if user.failed_attempts >= maxf:
            user.locked_until = now + timedelta(seconds=int(cfg.get("LOGIN_LOCKOUT_SECONDS", 900)))
            user.failed_attempts = 0
            locked = True
        db.session.commit()
        audit("login_fail", target=f"user:{user.id}",
              detail={"locked": locked}, result="denied")
        return fail("用户名或密码错误" + ("（多次失败，账号已临时锁定）" if locked else ""), 401)

    # 成功：清零失败计数、刷新最近登录时间、签发会话
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    _, raw, csrf = start_session(user)
    g.current_user = user
    g.current_perms = _perms_of(user)
    g.current_scope = resolve_scope(user.id)
    db.session.commit()
    audit("login_ok", target=f"user:{user.id}")

    resp = ok(_identity_payload(user))
    return apply_session_cookies(resp, raw, csrf)


@bp.post("/logout")
def logout():
    user = current_user()
    sess = getattr(g, "current_session", None)
    if sess is not None:
        sess.revoked_at = datetime.now()
        db.session.commit()
    if user:
        audit("logout", target=f"user:{user.id}")
    return clear_session_cookies(ok({"logged_out": True}))


@bp.get("/me")
def me():
    """守卫已确认会话有效（本路径不在匿名白名单里），这里只做身份回显"""
    user = current_user()
    if not user:
        return fail("未登录或登录已过期", 401)
    return ok(_identity_payload(user))


# =============================================================================
# 内部工具
# =============================================================================

def _perms_of(user: SystemUser) -> set:
    """委托 security.resolve_perms（DB 为准，表未物化时回退 ROLE_SEED）"""
    from security import resolve_perms
    return resolve_perms(user.id)


def _identity_payload(user: SystemUser) -> dict:
    scope = getattr(g, "current_scope", None) or resolve_scope(user.id)
    return {
        "username": user.username,
        "display_name": user.display_name,
        "roles": [r.role_code for r in user.roles],
        "permissions": sorted(getattr(g, "current_perms", _perms_of(user))),
        "scope": "all" if scope.all else scope.key()[:200],
        "must_change_password": bool(user.must_change_password),
    }
