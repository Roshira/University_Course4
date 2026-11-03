"""Інтеграційний тест запущеного стека (docker compose up -d).

Перевіряє систему ззовні, як користувач: усі запити йдуть через nginx-шлюз (за замовчуванням :8080).
Потрібен лише Python 3.9+ без сторонніх пакетів.

    python tests/integration_test.py
    python tests/integration_test.py --base http://localhost:8081 --user admin --password admin12345

Тест створює тимчасового користувача-viewer і видаляє його наприкінці. Для перевірки блокування
після невдалих входів використовується окремий неіснуючий логін, тож адміністратора тест не блокує.
Код виходу 0, якщо всі перевірки пройдено.
"""
import argparse
import http.cookiejar
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

EXPECTED_JOBS = {"prometheus", "postgres-exporter", "db-monitor", "telemetry-api", "traffic-generator",
                 "ingest-worker", "auth-server", "rabbitmq", "loki", "tempo", "alloy", "grafana"}
EXPECTED_LOG_SERVICES = {"telemetry-api", "traffic-generator", "ingest-worker", "db-monitor", "auth-server",
                         "postgres", "rabbitmq", "gateway", "grafana", "prometheus", "loki", "tempo", "alloy"}
PIPELINE_SPANS = {("traffic-generator", "generator.session"), ("traffic-generator", "telemetry.events publish"),
                  ("ingest-worker", "rabbitmq.consume"),
                  ("telemetry-api", "POST api/Telemetry/track"), ("telemetry-api", "telemetry.write")}
DASHBOARDS = {"db-overview", "db-postgres", "db-analytics", "db-logs-traces"}
# панелі, які в нормальному стані можуть бути порожніми (помилки, блокування, DLQ тощо)
MAY_BE_EMPTY = re.compile(r"помилк|DLQ|dead|блокув|Deadlocks|Повільні|невдал|Останні помилки|Сервісів DOWN|"
                          r"Найдовший|Очікують", re.IGNORECASE)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)

    def request(self, method: str, path: str, data=None, headers=None, json_body=None, timeout=30):
        body = None
        headers = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        elif data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def get_json(self, path: str, **kw):
        status, _, body = self.request("GET", path, **kw)
        if status != 200:
            raise AssertionError(f"GET {path} -> {status}: {body[:200]!r}")
        return json.loads(body)

    def login(self, user: str, password: str, next_url: str = "/"):
        return self.request("POST", "/auth/login", data={"username": user, "password": password, "next": next_url})


class Runner:
    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, name: str, fn):
        try:
            detail = fn()
            self.passed += 1
            print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
        except Exception as e:  # noqa: BLE001 — будь-яка помилка перевірки = провал
            self.failed.append(name)
            print(f"  FAIL  {name}: {e}")

    def section(self, title: str):
        print(f"\n== {title}")


def location(headers: dict) -> str:
    return headers.get("Location") or headers.get("location") or ""


def prom_query(admin: Client, expr: str):
    q = urllib.parse.quote(expr)
    data = admin.get_json(f"/prometheus/api/v1/query?query={q}")
    return data["data"]["result"]


def prom_value(admin: Client, expr: str) -> float:
    res = prom_query(admin, expr)
    return float(res[0]["value"][1]) if res else 0.0


def tempo_query(admin: Client, target: dict) -> int:
    """TraceQL-пошук і service map Grafana 11 виконує в браузері, тому тут іде прямо в Tempo / Prometheus."""
    if target.get("queryType") == "serviceMap":
        return int(prom_value(admin, "count(traces_service_graph_request_total)"))
    q = urllib.parse.quote(target.get("query", "{}"))
    limit = target.get("limit", 20)
    now = int(time.time())
    res = admin.get_json(f"/api/datasources/proxy/uid/tempo/api/search?q={q}&limit={limit}"
                         f"&start={now - 1800}&end={now}")
    return len(res.get("traces", []))


def ds_query(admin: Client, uid: str, target: dict, frm="now-15m"):
    if uid == "tempo":
        return tempo_query(admin, target)
    query = {k: v for k, v in target.items() if k != "datasource"}
    query.update({"datasource": {"uid": uid}, "refId": target.get("refId", "A"),
                  "intervalMs": 15000, "maxDataPoints": 300})
    status, _, body = admin.request("POST", "/api/ds/query", json_body={
        "queries": [query], "from": frm, "to": "now"}, timeout=60)
    data = json.loads(body or b"{}")
    result = (data.get("results") or {}).get(query["refId"], {})
    if status != 200 or result.get("error"):
        raise AssertionError(result.get("error") or f"HTTP {status}: {body[:200]!r}")
    rows = 0
    for frame in result.get("frames", []):
        values = frame.get("data", {}).get("values", [])
        if values:
            rows += max(len(v) for v in values)
    return rows


def wait_for(fn, timeout: float, step: float = 3):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(step)
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin12345")
    args = ap.parse_args()

    run = Runner()
    anon = Client(args.base)
    admin = Client(args.base)
    viewer = Client(args.base)
    viewer_name = "itest_" + secrets.token_hex(3)
    viewer_pass = secrets.token_urlsafe(12)

    # ------------------------------------------------------------------ auth
    run.section("Шлюз і авторизація")

    def anon_redirects():
        status, headers, _ = anon.request("GET", "/")
        assert status == 302 and location(headers).startswith("/d/db-overview"), f"/ -> {location(headers)}"
        for path in ("/d/db-overview", "/prometheus/", "/rabbitmq/", "/api/user", "/api/datasources"):
            status, headers, _ = anon.request("GET", path)
            assert status == 302 and "/auth/login" in location(headers), f"{path} -> {status} {location(headers)}"
        return "6 захищених адрес"
    run.check("без входу захищені адреси перенаправляють на /auth/login", anon_redirects)

    def spoofed_header():
        status, headers, _ = anon.request("GET", "/api/user", headers={"X-WEBAUTH-USER": "admin",
                                                                      "X-WEBAUTH-ROLE": "Admin"})
        assert status == 302 and "/auth/login" in location(headers), f"{status}"
    run.check("підроблений X-WEBAUTH-USER без cookie не дає доступу", spoofed_header)

    def wrong_password():
        status, _, _ = Client(args.base).login(args.user, "definitely-wrong-" + secrets.token_hex(4))
        assert status == 401, status
    run.check("невірний пароль -> 401", wrong_password)

    def no_header_injection():
        # закодований перенос рядка в шляху не повинен стати заголовком відповіді (CRLF injection)
        status, headers, _ = anon.request("GET", "/x%0d%0aSet-Cookie:%20pwn=1")
        assert status == 302, status
        assert not any(k.lower() == "set-cookie" and "pwn" in v for k, v in headers.items()), headers
        assert "pwn=1" not in location(headers), location(headers)
    run.check("CRLF у шляху не дає вставити заголовок відповіді", no_header_injection)

    def next_keeps_query():
        status, headers, _ = anon.request("GET", "/d/db-postgres?from=now-1h&to=now")
        if location(headers).startswith("/auth/start-login"):
            status, headers, _ = anon.request("GET", location(headers))
        loc = location(headers)
        nxt = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("next", [""])[0]
        assert nxt == "/d/db-postgres?from=now-1h&to=now", loc
        return nxt
    run.check("після входу користувач повертається на ту саму адресу з параметрами", next_keeps_query)

    def metrics_not_public():
        for path in ("/metrics", "/api/telemetry/metrics"):
            status, _, body = anon.request("GET", path)
            assert not (status == 200 and b"# HELP" in body), f"{path} віддає метрики без входу"
    run.check("метрики сервісів не доступні ззовні без входу", metrics_not_public)

    def admin_login():
        status, headers, _ = admin.login(args.user, args.password)
        assert status == 303, f"{status}"
        me = admin.get_json("/auth/me")
        assert me.get("role") == "admin", me
    run.check("вхід адміністратора", admin_login)

    def open_redirect():
        c = Client(args.base)
        for evil in ("//evil.example", "https://evil.example/", "/\\evil.example", "/%2F%2Fevil.example"):
            status, headers, _ = c.login(args.user, args.password, next_url=evil)
            loc = location(headers)
            host = urllib.parse.urlparse(urllib.parse.urljoin(args.base + "/", loc)).hostname
            assert host == urllib.parse.urlparse(args.base).hostname, f"next={evil!r} -> {loc!r}"
        return "4 варіанти"
    run.check("параметр next не дозволяє редірект на інший сайт", open_redirect)

    def admin_grafana():
        user = admin.get_json("/api/user")
        assert user["login"] == args.user and user.get("isGrafanaAdmin"), user
        orgs = admin.get_json("/api/user/orgs")
        assert orgs[0]["role"] == "Admin", orgs
    run.check("Grafana бачить користувача з роллю Admin", admin_grafana)

    def admin_prometheus():
        status, _, _ = admin.request("GET", "/prometheus/api/v1/status/buildinfo")
        assert status == 200, status
        status, _, _ = admin.request("GET", "/rabbitmq/")
        assert status == 200, f"/rabbitmq/ -> {status}"
    run.check("admin має доступ до /prometheus/ і /rabbitmq/", admin_prometheus)

    def csrf_blocked():
        for headers in ({"Origin": "http://evil.example"}, {}):
            status, _, _ = admin.request("POST", "/auth/users", headers=headers,
                                         data={"username": "csrf_" + viewer_name, "password": viewer_pass,
                                               "role": "admin"})
            assert status == 403, f"{headers} -> {status}"
    run.check("форми адміністратора захищені від CSRF (чужий або відсутній Origin -> 403)", csrf_blocked)

    def create_viewer():
        status, _, _ = admin.request("POST", "/auth/users", headers={"Origin": args.base},
                                     data={"username": viewer_name, "password": viewer_pass, "role": "viewer"})
        assert status == 303, status
        status, _, _ = viewer.login(viewer_name, viewer_pass)
        assert status == 303, f"login {status}"
    run.check("admin створює viewer, viewer входить", create_viewer)

    def viewer_rights():
        orgs = viewer.get_json("/api/user/orgs")
        assert orgs[0]["role"] == "Viewer", orgs
        status, _, _ = viewer.request("GET", "/api/dashboards/uid/db-overview")
        assert status == 200, f"dashboard {status}"
        for path in ("/prometheus/", "/rabbitmq/"):
            status, headers, _ = viewer.request("GET", path)
            assert status in (302, 403) and "/prometheus" not in location(headers), f"{path} -> {status}"
        status, _, body = viewer.request("GET", "/auth/users")
        assert viewer_name.encode() not in body or "Доступ заборонено".encode() in body, "viewer бачить список"
        status, _, _ = viewer.request("POST", "/auth/users", headers={"Origin": args.base},
                                      data={"username": "x" + viewer_name, "password": "longpassword1",
                                            "role": "admin"})
        users = admin.request("GET", "/auth/users")[2]
        assert f"/auth/users/x{viewer_name}/delete".encode() not in users, "viewer зміг створити користувача"
        status, _, _ = viewer.request("POST", "/api/dashboards/db", json_body={
            "dashboard": {"title": "itest", "uid": None}, "overwrite": False})
        assert status in (401, 403), f"viewer створив дашборд: {status}"
    run.check("viewer бачить дашборди, але не адмін-зони і не може нічого змінювати", viewer_rights)

    def logout_revokes():
        old = list(viewer.jar)
        viewer.request("GET", "/auth/logout")
        replay = Client(args.base)
        for cookie in old:
            replay.jar.set_cookie(cookie)
        status, headers, _ = replay.request("GET", "/d/db-overview")
        assert status == 302 and "/auth/login" in location(headers), f"старий cookie працює: {status}"
    run.check("після виходу старий cookie більше не працює", logout_revokes)

    def lockout():
        c = Client(args.base)
        name = "itest_lock_" + secrets.token_hex(3)
        codes = [c.login(name, "wrong")[0] for _ in range(6)]
        assert codes[:5] == [401] * 5 and codes[5] == 429, codes
    run.check("6-та невдала спроба входу поспіль блокується (429)", lockout)

    def api_case_insensitive():
        # Swagger генерує /api/Auth/login: запит має дійти до API (401), а не піти в Grafana (302)
        status, _, _ = anon.request("POST", "/api/Auth/login",
                                    json_body={"email": "nobody@example.com", "password": "x"})
        assert status in (400, 401), status
        status, _, body = anon.request("GET", "/swagger/v1/swagger.json")
        assert status == 200 and b"/api/Telemetry/track" in body, status
    run.check("API курсової доступне через шлюз без урахування регістру; Swagger працює", api_case_insensitive)

    def no_dev_error_page():
        status, _, body = anon.request("POST", "/api/telemetry/track", data={"a": "b"})
        assert b"Exception" not in body and b"   at " not in body, body[:200]
        return f"HTTP {status}"
    run.check("API працює в Production: без стектрейсів у відповідях", no_dev_error_page)

    # ------------------------------------------------------------------ prometheus
    run.section("Prometheus")

    def targets_up():
        targets = admin.get_json("/prometheus/api/v1/targets?state=active")["data"]["activeTargets"]
        jobs = {t["labels"]["job"] for t in targets}
        down = [f'{t["labels"]["job"]}: {t.get("lastError")}' for t in targets if t["health"] != "up"]
        assert EXPECTED_JOBS <= jobs, f"немає: {EXPECTED_JOBS - jobs}"
        assert not down, down
        workers = sum(1 for t in targets if t["labels"]["job"] == "ingest-worker")
        assert workers == 2, f"ingest-worker targets: {workers}"
        return f"{len(targets)} цілей up"
    run.check("усі цілі в стані up (ingest-worker — 2 репліки)", targets_up)

    def rules_loaded():
        groups = admin.get_json("/prometheus/api/v1/rules")["data"]["groups"]
        rules = [r for g in groups for r in g["rules"] if r["type"] == "alerting"]
        bad = [r["name"] for r in rules if r.get("health") != "ok"]
        assert len(rules) >= 12 and not bad, f"{len(rules)} правил, з помилкою: {bad}"
        return f"{len(rules)} правил"
    run.check("правила алертів завантажені без помилок", rules_loaded)

    def no_critical_alerts():
        alerts = admin.get_json("/prometheus/api/v1/alerts")["data"]["alerts"]
        firing = [a["labels"]["alertname"] for a in alerts
                  if a["state"] == "firing" and a["labels"].get("severity") == "critical"]
        assert not firing, firing
        return f"активних алертів усього: {sum(a['state'] == 'firing' for a in alerts)}"
    run.check("немає критичних алертів", no_critical_alerts)

    def tsdb_retention():
        flags = admin.get_json("/prometheus/api/v1/status/flags")["data"]
        assert flags.get("storage.tsdb.retention.time") == "15d", flags.get("storage.tsdb.retention.time")
    run.check("TSDB зберігає дані 15 днів", tsdb_retention)

    # ------------------------------------------------------------------ pipeline
    run.section("Конвеєр даних і БД")

    def events_flow():
        a = prom_value(admin, "sum(telemetry_events_written_total)")
        time.sleep(15)
        b = prom_value(admin, "sum(telemetry_events_written_total)")
        assert b > a, f"{a} -> {b}"
        return f"+{int(b - a)} подій за 15 с"
    run.check("нові події записуються в PostgreSQL", events_flow)

    def stages_consistent():
        pub = prom_value(admin, "sum(rate(generator_events_published_total[2m]))")
        ok = prom_value(admin, 'sum(rate(consumer_messages_processed_total{result="ok"}[2m]))')
        written = prom_value(admin, "sum(rate(telemetry_events_written_total[2m]))")
        assert pub > 0 and abs(ok - pub) / pub < 0.2 and abs(written - pub) / pub < 0.2, (pub, ok, written)
        return f"опубліковано {pub:.1f}/с, оброблено {ok:.1f}/с, записано {written:.1f}/с"
    run.check("опубліковано ≈ оброблено ≈ записано", stages_consistent)

    def queues_ok():
        res = {r["metric"].get("queue"): float(r["value"][1])
               for r in prom_query(admin, "rabbitmq_queue_messages_ready")}
        assert res.get("telemetry.events", 0) < 1000, res
        assert res.get("telemetry.events.dead", 0) == 0, res
        return str(res)
    run.check("черга не накопичується, DLQ порожня", queues_ok)

    def db_rows():
        n = ds_query(admin, "postgres", {"refId": "A", "format": "table", "rawQuery": True,
                                          "rawSql": 'SELECT count(*) AS n FROM "Events"'})
        assert n == 1
        return "SELECT через grafana_ro працює"
    run.check("Grafana читає таблиці БД (користувач grafana_ro)", db_rows)

    def readonly_user():
        try:
            ds_query(admin, "postgres", {"refId": "A", "format": "table", "rawQuery": True,
                                         "rawSql": 'DELETE FROM "Events" WHERE false'})
        except AssertionError as e:
            assert "permission denied" in str(e).lower(), e
            return "DELETE заборонено"
        raise AssertionError("grafana_ro зміг виконати DELETE")
    run.check("користувач grafana_ro не може змінювати дані", readonly_user)

    def no_secrets_in_query_labels():
        series = admin.get_json("/prometheus/api/v1/series?" + urllib.parse.urlencode(
            {"match[]": "db_top_query_calls", "start": str(int(time.time()) - 120)}))["data"]
        bad = [s["query"] for s in series
               if not re.match(r"\s*(select|insert|update|delete|with)\b", s.get("query", ""), re.IGNORECASE)]
        assert series and not bad, bad[:3]
        return f"{len(series)} запитів, лише DML"
    run.check("у метриках топ-запитів лише DML (без CREATE ROLE ... PASSWORD)", no_secrets_in_query_labels)

    def hashes_hidden():
        try:
            ds_query(admin, "postgres", {"refId": "A", "format": "table", "rawQuery": True,
                                         "rawSql": 'SELECT "PasswordHash" FROM "Companies" LIMIT 1'})
        except AssertionError as e:
            assert "permission denied" in str(e).lower(), e
            return "PasswordHash недоступний"
        raise AssertionError("grafana_ro читає хеші паролів")
    run.check("Grafana не бачить хешів паролів компаній", hashes_hidden)

    def db_monitor_metrics():
        n = prom_value(admin, "count(db_top_query_mean_ms)")
        size = prom_value(admin, 'max(db_table_size_bytes{table="Events"})')
        assert n > 0 and size > 0, (n, size)
        return f"топ-запитів: {int(n)}, Events: {size / 1e6:.1f} МБ"
    run.check("db-monitor віддає метрики з pg_stat_statements і таблиць", db_monitor_metrics)

    # ------------------------------------------------------------------ logs & traces
    run.section("Логи (Loki) і трейси (Tempo)")

    def loki_services():
        q = urllib.parse.quote('sum by (service) (count_over_time({service=~".+"}[30m]))')
        res = admin.get_json(f"/api/datasources/proxy/uid/loki/loki/api/v1/query?query={q}")["data"]["result"]
        services = {r["metric"]["service"] for r in res}
        missing = EXPECTED_LOG_SERVICES - services
        assert not missing, f"немає логів від: {missing}"
        return f"{len(services)} сервісів"
    run.check("у Loki є логи всіх сервісів", loki_services)

    def loki_labels():
        labels = set(admin.get_json("/api/datasources/proxy/uid/loki/loki/api/v1/labels")["data"])
        assert {"service", "level"} <= labels, labels
        # значення лейбла level за останні 2 хв (endpoint label/values неточний за часом — береться запит)
        q = urllib.parse.quote('sum by (level) (count_over_time({service=~".+"}[2m]))')
        res = admin.get_json(f"/api/datasources/proxy/uid/loki/loki/api/v1/query?query={q}")["data"]["result"]
        unexpected = {r["metric"].get("level") for r in res} - {"error", "warning", "info", "debug"}
        assert not unexpected, f"ненормалізовані рівні: {unexpected}"
        assert not labels & {"trace_id", "TraceId", "session_id"}, f"висока кардинальність: {labels}"
        return ", ".join(sorted(labels))
    run.check("лейбли Loki: service, level; trace_id не є лейблом", loki_labels)

    trace_holder = {}

    def log_to_trace():
        def find():
            now = int(time.time())
            q = urllib.parse.quote('{service="traffic-generator"} |= "Session published"')
            res = admin.get_json(f"/api/datasources/proxy/uid/loki/loki/api/v1/query_range?query={q}"
                                 f"&limit=5&start={(now - 300) * 10**9}&end={(now - 20) * 10**9}")["data"]["result"]
            for stream in res:
                for _, line in stream["values"]:
                    return json.loads(line).get("trace_id")
        tid = wait_for(find, 60)
        assert tid and re.fullmatch(r"[0-9a-f]{32}", tid), tid
        trace_holder["id"] = tid
        return tid
    run.check("рядок логу генератора містить trace_id", log_to_trace)

    def full_trace():
        tid = trace_holder["id"]
        data = admin.get_json(f"/api/datasources/proxy/uid/tempo/api/traces/{tid}")
        spans, parents = set(), {}
        for batch in data.get("batches", data.get("resourceSpans", [])):
            svc = next(a["value"]["stringValue"] for a in batch["resource"]["attributes"] if a["key"] == "service.name")
            for scope in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
                for s in scope["spans"]:
                    spans.add((svc, s["name"]))
        missing = PIPELINE_SPANS - spans
        assert not missing, f"немає спанів: {missing}"
        assert any(svc == "telemetry-api" and name not in ("POST api/Telemetry/track", "telemetry.write")
                   for svc, name in spans), "немає SQL-спану Npgsql"
        return f"{len(spans)} різних спанів"
    run.check("трейс із логу проходить generator -> RabbitMQ -> worker -> API -> INSERT", full_trace)

    def trace_metrics():
        a = prom_value(admin, "count(traces_service_graph_request_total)")
        b = prom_value(admin, "count(traces_spanmetrics_calls_total)")
        assert a > 0 and b > 0, (a, b)
        edges = {(r["metric"].get("client"), r["metric"].get("server"))
                 for r in prom_query(admin, "traces_service_graph_request_total")}
        assert ("traffic-generator", "ingest-worker") in edges, sorted(edges)
        return f"ребер у графі: {len(edges)}"
    run.check("Tempo генерує service graph (є ребро generator -> ingest-worker) і span-metrics", trace_metrics)

    # ------------------------------------------------------------------ grafana
    run.section("Grafana: джерела даних і кожна панель дашбордів")

    def datasources():
        ds = {d["uid"]: d["type"] for d in admin.get_json("/api/datasources")}
        assert {"prometheus", "loki", "tempo", "postgres"} <= set(ds), ds
        for uid in ("prometheus", "loki", "postgres"):
            h = admin.get_json(f"/api/datasources/uid/{uid}/health")
            assert h.get("status") == "OK", (uid, h)
    run.check("джерела даних Prometheus, Loki, PostgreSQL доступні; Tempo налаштовано", datasources)

    def dashboards_present():
        found = {d["uid"] for d in admin.get_json("/api/search?type=dash-db")}
        assert DASHBOARDS <= found, DASHBOARDS - found
    run.check("усі 4 дашборди створені", dashboards_present)

    variables = {"$service": ".+", "${service:regex}": ".+", "$level": ".+", "${level:regex}": ".+",
                 "$search": "", "${search}": "", "$__all": ".+"}

    def expand(value):
        if isinstance(value, str):
            for k in sorted(variables, key=len, reverse=True):
                value = value.replace(k, variables[k])
        return value

    for uid in sorted(DASHBOARDS):
        dash = admin.get_json(f"/api/dashboards/uid/{uid}")["dashboard"]

        def panels(items):
            for p in items:
                if p.get("type") == "row":
                    yield from panels(p.get("panels", []))
                else:
                    yield p

        for panel in panels(dash.get("panels", [])):
            if not panel.get("targets"):
                continue

            def check_panel(panel=panel):
                total = 0
                for t in panel["targets"]:
                    ds = t.get("datasource") or panel.get("datasource") or {}
                    target = {k: expand(v) for k, v in t.items()}
                    total += ds_query(admin, ds.get("uid"), target, frm="now-30m")
                if total == 0 and not MAY_BE_EMPTY.search(panel.get("title", "")):
                    raise AssertionError("порожня панель")
                return f"{total} рядків/точок"
            run.check(f"[{uid}] {panel.get('title')}", check_panel)

    # ------------------------------------------------------------------ cleanup
    run.section("Прибирання")
    def cleanup():
        admin.request("POST", f"/auth/users/{viewer_name}/delete", headers={"Origin": args.base})
        users = admin.request("GET", "/auth/users")[2]
        assert f"/auth/users/{viewer_name}/delete".encode() not in users, "користувача не видалено"
    run.check(f"видалення тимчасового користувача {viewer_name}", cleanup)

    print(f"\nПройдено: {run.passed}, не пройдено: {len(run.failed)}")
    for name in run.failed:
        print(f"  - {name}")
    return 1 if run.failed else 0


if __name__ == "__main__":
    sys.exit(main())
