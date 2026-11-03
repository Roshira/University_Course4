"""Сервер авторизації (Python 3 + FastAPI + SQLite).

Захищає весь моніторинговий контур (Grafana, Prometheus, RabbitMQ UI): nginx перед кожним
запитом робить підзапит auth_request -> GET /auth/verify. Якщо cookie сесії валідна —
повертаємо 200 і заголовки X-User / X-Role, які nginx передає в Grafana (auth.proxy);
інакше 401 і nginx перенаправляє на /auth/login.

Таблиці SQLite:
  users        — користувачі (pbkdf2-sha256 хеш пароля, роль admin/editor/viewer)
  sessions     — видані сесії (можна відкликати при logout)
  login_events — журнал спроб входу (аудит + захист від перебору паролів)
"""
import hashlib
import hmac
import html
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
from contextlib import contextmanager

import jwt
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

from common.obs import log_extra, setup_logging, setup_tracing

SERVICE = "auth-server"
log = setup_logging(SERVICE)
tracer = setup_tracing(SERVICE)

DB_PATH = os.getenv("AUTH_DB_PATH", "/data/auth.db")
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", str(8 * 3600)))
COOKIE = "obs_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
MAX_FAILS, FAIL_WINDOW = 5, 300
LOGIN_EVENTS_TTL = 30 * 24 * 3600          # журнал входів зберігаємо 30 днів
USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
ROLES = ("admin", "editor", "viewer")
GRAFANA_ROLE = {"admin": "Admin", "editor": "Editor", "viewer": "Viewer"}

LOGINS = Counter("auth_logins_total", "Спроби входу", ["result"])
VERIFY = Counter("auth_verify_total", "Перевірки доступу від nginx", ["result"])
USERS = Gauge("auth_users_total", "Кількість користувачів")
ACTIVE_SESSIONS = Gauge("auth_active_sessions", "Активні (не відкликані й не прострочені) сесії")
# серії з нулем одразу після старту, інакше increase() не бачить першого входу
for _result in ("success", "failure", "locked"):
    LOGINS.labels(_result)
for _result in ("ok", "unauthorized", "forbidden"):
    VERIFY.labels(_result)

app = FastAPI(title="Observability Auth Server", docs_url=None, redoc_url=None)
FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics,auth/verify")


# ------------------------------------------------------------------ storage
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)).split("$")[2], digest_hex)


def load_secret() -> str:
    """Ключ підпису JWT. Якщо AUTH_SECRET не задано, генеруємо випадковий і зберігаємо поруч із БД:
    так немає публічного ключа "за замовчуванням", а сесії переживають перезапуск контейнера."""
    if os.getenv("AUTH_SECRET"):
        return os.environ["AUTH_SECRET"]
    path = os.path.join(os.path.dirname(DB_PATH) or ".", "auth_secret")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip()


SECRET = load_secret()
# фіктивний хеш: для неіснуючого логіна теж рахуємо PBKDF2, щоб за часом відповіді не можна було
# дізнатися, які логіни існують
DUMMY_HASH = hash_password(secrets.token_hex(8))


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin','editor','viewer')),
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT, ip TEXT, success INTEGER, ts INTEGER
            );
            CREATE INDEX IF NOT EXISTS ix_login_events_user_ts ON login_events(username, ts);
        """)
        admin = os.getenv("ADMIN_USERNAME", "admin")
        if not c.execute("SELECT 1 FROM users WHERE username = ?", (admin,)).fetchone():
            c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
                      (admin, hash_password(os.getenv("ADMIN_PASSWORD", "admin")), "admin", int(time.time())))
            log.info("Default admin user created", extra=log_extra(user=admin))
    refresh_gauges()


def refresh_gauges():
    with db() as c:
        USERS.set(c.execute("SELECT count(*) FROM users").fetchone()[0])
        ACTIVE_SESSIONS.set(c.execute("SELECT count(*) FROM sessions WHERE revoked = 0 AND expires_at > ?",
                                      (int(time.time()),)).fetchone()[0])


init_db()


# ------------------------------------------------------------------ sessions
def current_user(request: Request) -> sqlite3.Row | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    with db() as c:
        sess = c.execute("SELECT * FROM sessions WHERE id = ? AND revoked = 0 AND expires_at > ?",
                         (claims.get("sid"), int(time.time()))).fetchone()
        if not sess:
            return None
        return c.execute("SELECT * FROM users WHERE username = ?", (sess["username"],)).fetchone()


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def safe_next(url: str | None) -> str:
    """Дозволяємо лише відносні шляхи цього ж сайту: без //host, зворотних слешів і керуючих символів."""
    if (url and url.startswith("/") and not url.startswith(("//", "/\\"))
            and "\\" not in url and url.isprintable()):
        return url
    return "/"


def same_origin(request: Request) -> bool:
    """Захист від CSRF для форм адміністратора: запит має прийти зі сторінки цього ж сайту."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return False
    return urllib.parse.urlsplit(origin).netloc == request.headers.get("host")


# ------------------------------------------------------------------ HTML
STYLE = """
<style>
 :root{--bg:#0f1218;--card:#181c25;--fg:#e6e8ee;--mut:#8b93a7;--acc:#f46800;--err:#ff5d5d;--line:#2a3040}
 *{box-sizing:border-box} body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
 .wrap{max-width:420px;margin:10vh auto;padding:0 16px} .wide{max-width:900px;margin:5vh auto}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:28px}
 h1{font-size:22px;margin:0 0 4px} p.m{color:var(--mut);margin:0 0 20px}
 label{display:block;font-size:13px;color:var(--mut);margin:12px 0 4px}
 input,select{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--line);background:#11141b;color:var(--fg);font-size:15px}
 button{margin-top:18px;width:100%;padding:11px;border:0;border-radius:8px;background:var(--acc);color:#fff;font-weight:600;font-size:15px;cursor:pointer}
 .err{background:#3a1717;border:1px solid var(--err);color:#ffb3b3;padding:10px 12px;border-radius:8px;margin-bottom:8px}
 table{width:100%;border-collapse:collapse;font-size:14px} td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left}
 a{color:var(--acc)} .row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1;min-width:140px}
 .sm{width:auto;margin:0;padding:6px 10px;font-size:13px;background:#3a2a2a}
</style>"""


def page(body: str, wide=False) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang='uk'><head><meta charset='utf-8'>"
                        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        f"<title>Моніторинг — вхід</title>{STYLE}</head>"
                        f"<body><div class='wrap {'wide' if wide else ''}'><div class='card'>{body}</div></div></body></html>")


def login_form(next_url: str, error: str = "", status: int = 200) -> HTMLResponse:
    err = f"<div class='err'>{html.escape(error)}</div>" if error else ""
    resp = page(f"""
        <h1>Система моніторингу БД</h1><p class='m'>AnalyticsSystem · Grafana · Prometheus · Loki · Tempo</p>
        {err}
        <form method='post' action='/auth/login'>
          <input type='hidden' name='next' value='{html.escape(next_url)}'>
          <label>Логін</label><input name='username' autocomplete='username' required autofocus>
          <label>Пароль</label><input name='password' type='password' autocomplete='current-password' required>
          <button type='submit'>Увійти</button>
        </form>""")
    resp.status_code = status
    return resp


# ------------------------------------------------------------------ routes
@app.get("/auth/start-login")
def start_login(request: Request):
    """nginx звертається сюди, коли запит без входу (error_page 401). Адресу, яку хотів відкрити
    користувач, nginx передає в X-Original-URI як є ($request_uri); тут вона URL-кодується в next."""
    original = safe_next(request.headers.get("x-original-uri"))
    return RedirectResponse("/auth/login?next=" + urllib.parse.quote(original, safe=""), status_code=302)


@app.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if current_user(request):
        return RedirectResponse(safe_next(next), status_code=303)
    return login_form(safe_next(next))


@app.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    ip, now = client_ip(request), int(time.time())
    username = username.strip()[:64]
    with db() as c:
        # блокуємо пару (логін, IP): так перебір паролів зупиняється, а заблокувати чужий акаунт
        # (наприклад admin) з іншої адреси не вийде
        fails = c.execute("SELECT count(*) FROM login_events WHERE username = ? AND ip = ? AND success = 0 AND ts > ?",
                          (username, ip, now - FAIL_WINDOW)).fetchone()[0]
        if fails >= MAX_FAILS:
            LOGINS.labels("locked").inc()
            log.warning("Login blocked: too many failures", extra=log_extra(user=username, ip=ip))
            return login_form(safe_next(next), "Забагато невдалих спроб. Спробуйте через 5 хвилин.", 429)

        user = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        ok = check_password(password, user["password_hash"] if user else DUMMY_HASH) and bool(user)
        c.execute("INSERT INTO login_events (username, ip, success, ts) VALUES (?,?,?,?)",
                  (username, ip, int(ok), now))
        if not ok:
            LOGINS.labels("failure").inc()
            log.warning("Login failed", extra=log_extra(user=username, ip=ip))
            return login_form(safe_next(next), "Невірний логін або пароль", 401)

        sid = secrets.token_urlsafe(24)
        # прибирання: прострочені сесії та старий журнал входів
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        c.execute("DELETE FROM login_events WHERE ts < ?", (now - LOGIN_EVENTS_TTL,))
        c.execute("INSERT INTO sessions (id, username, created_at, expires_at) VALUES (?,?,?,?)",
                  (sid, username, now, now + SESSION_TTL))
    token = jwt.encode({"sid": sid, "sub": username, "role": user["role"], "exp": now + SESSION_TTL},
                       SECRET, algorithm="HS256")
    LOGINS.labels("success").inc()
    log.info("Login success", extra=log_extra(user=username, ip=ip, role=user["role"]))
    refresh_gauges()
    resp = RedirectResponse(safe_next(next), status_code=303)
    resp.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax",
                    secure=COOKIE_SECURE, path="/")
    return resp


@app.get("/auth/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        try:
            sid = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False}).get("sid")
            with db() as c:
                c.execute("UPDATE sessions SET revoked = 1 WHERE id = ?", (sid,))
        except jwt.PyJWTError:
            pass
    refresh_gauges()
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/auth/verify")
def verify(request: Request, role: str | None = None):
    """Викликається nginx (auth_request). ?role=admin — доступ лише адміністраторам."""
    user = current_user(request)
    if not user:
        VERIFY.labels("unauthorized").inc()
        return Response(status_code=401)
    if role == "admin" and user["role"] != "admin":
        VERIFY.labels("forbidden").inc()
        return Response(status_code=403)
    VERIFY.labels("ok").inc()
    return Response(status_code=200, headers={
        "X-User": user["username"],
        "X-Role": GRAFANA_ROLE[user["role"]],
    })


@app.get("/auth/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "username": user["username"], "role": user["role"]}


# ---------- адміністрування користувачів (тільки admin)
def require_admin(request: Request):
    user = current_user(request)
    if not user:
        return None, RedirectResponse("/auth/login?next=/auth/users", status_code=303)
    if user["role"] != "admin":
        return None, page("<h1>Доступ заборонено</h1><p class='m'>Потрібна роль admin.</p><a href='/'>На головну</a>")
    return user, None


@app.get("/auth/users", response_class=HTMLResponse)
def users_page(request: Request, msg: str = ""):
    admin, denied = require_admin(request)
    if denied:
        return denied
    with db() as c:
        users = c.execute("SELECT username, role, created_at FROM users ORDER BY id").fetchall()
        events = c.execute("SELECT username, ip, success, ts FROM login_events ORDER BY id DESC LIMIT 15").fetchall()
    rows = "".join(
        f"<tr><td>{html.escape(u['username'])}</td><td>{u['role']}</td>"
        f"<td>{time.strftime('%Y-%m-%d %H:%M', time.localtime(u['created_at']))}</td><td>"
        + ("" if u["username"] == admin["username"] else
           f"<form method='post' action='/auth/users/{urllib.parse.quote(u['username'])}/delete' style='margin:0'>"
           f"<button class='sm'>Видалити</button></form>")
        + "</td></tr>" for u in users)
    ev = "".join(
        f"<tr><td>{time.strftime('%H:%M:%S', time.localtime(e['ts']))}</td><td>{html.escape(e['username'] or '')}</td>"
        f"<td>{html.escape(e['ip'] or '')}</td><td>{'✓' if e['success'] else '✗'}</td></tr>" for e in events)
    note = f"<div class='err' style='background:#1d2a1d;border-color:#3c7'>{html.escape(msg)}</div>" if msg else ""
    return page(f"""
        <h1>Користувачі</h1><p class='m'>Ви увійшли як <b>{html.escape(admin['username'])}</b> ·
        <a href='/'>Grafana</a> · <a href='/auth/logout'>Вийти</a></p>{note}
        <table><tr><th>Логін</th><th>Роль</th><th>Створено</th><th></th></tr>{rows}</table>
        <h1 style='margin-top:28px'>Додати користувача</h1>
        <form method='post' action='/auth/users' class='row'>
          <div><label>Логін</label><input name='username' required></div>
          <div><label>Пароль (мін. 8)</label><input name='password' type='password' minlength='8' required></div>
          <div><label>Роль</label><select name='role'>{''.join(f"<option>{r}</option>" for r in ROLES[::-1])}</select></div>
          <div><button>Створити</button></div>
        </form>
        <h1 style='margin-top:28px'>Останні входи</h1>
        <table><tr><th>Час</th><th>Логін</th><th>IP</th><th></th></tr>{ev}</table>""", wide=True)


@app.post("/auth/users")
def create_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("viewer")):
    admin, denied = require_admin(request)
    if denied:
        return denied
    if not same_origin(request):
        return Response("Запит не з цього сайту (CSRF)", status_code=403)
    username = username.strip()
    if role not in ROLES or len(password) < 8 or not USERNAME_RE.fullmatch(username):
        return RedirectResponse("/auth/users?msg=Некоректні+дані", status_code=303)
    try:
        with db() as c:
            c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
                      (username, hash_password(password), role, int(time.time())))
    except sqlite3.IntegrityError:
        return RedirectResponse("/auth/users?msg=Такий+користувач+вже+існує", status_code=303)
    log.info("User created", extra=log_extra(user=username, role=role, by=admin["username"]))
    refresh_gauges()
    return RedirectResponse("/auth/users?msg=Користувача+створено", status_code=303)


@app.post("/auth/users/{username}/delete")
def delete_user(request: Request, username: str):
    admin, denied = require_admin(request)
    if denied:
        return denied
    if not same_origin(request):
        return Response("Запит не з цього сайту (CSRF)", status_code=403)
    if username != admin["username"]:
        with db() as c:
            c.execute("DELETE FROM users WHERE username = ?", (username,))
            c.execute("UPDATE sessions SET revoked = 1 WHERE username = ?", (username,))
        log.info("User deleted", extra=log_extra(user=username, by=admin["username"]))
    refresh_gauges()
    return RedirectResponse("/auth/users?msg=Видалено", status_code=303)


# ---------- службові
@app.get("/metrics")
def metrics():
    refresh_gauges()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok"}
