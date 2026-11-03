"""Unit-тести сервера авторизації (запуск: див. tests/run_unit_tests.ps1 / README)."""
import os
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp()
os.environ["AUTH_DB_PATH"] = os.path.join(TMP, "auth.db")
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-test-pass"
os.environ.pop("AUTH_SECRET", None)
os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))   # services/ -> common
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))         # auth-server/ -> app

from fastapi.testclient import TestClient  # noqa: E402

import app as auth  # noqa: E402

HOST = "testserver"
ORIGIN = {"origin": f"http://{HOST}"}


def client(ip="10.0.0.1") -> TestClient:
    return TestClient(auth.app, headers={"x-real-ip": ip}, follow_redirects=False)


def login(c: TestClient, user="admin", password="admin-test-pass", next_url="/"):
    return c.post("/auth/login", data={"username": user, "password": password, "next": next_url})


class SafeNextTest(unittest.TestCase):
    def test_allows_local_paths(self):
        for url in ("/", "/d/db-overview?from=now-1h&to=now", "/prometheus/graph"):
            self.assertEqual(auth.safe_next(url), url)

    def test_rejects_external_and_tricky_urls(self):
        for url in (None, "", "https://evil.example", "//evil.example", "/\\evil.example",
                    "/a\\b", "/x\r\nSet-Cookie: a=1", "/x\tevil", "evil.example"):
            self.assertEqual(auth.safe_next(url), "/", url)


class PasswordTest(unittest.TestCase):
    def test_hash_roundtrip_and_salt(self):
        h1, h2 = auth.hash_password("secret-1"), auth.hash_password("secret-1")
        self.assertNotEqual(h1, h2)  # різна сіль
        self.assertTrue(auth.check_password("secret-1", h1))
        self.assertFalse(auth.check_password("secret-2", h1))
        self.assertFalse(auth.check_password("secret-1", "broken"))


class SecretTest(unittest.TestCase):
    def test_secret_generated_and_persisted(self):
        path = os.path.join(TMP, "auth_secret")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(auth.load_secret(), auth.SECRET)
        self.assertGreaterEqual(len(auth.SECRET), 32)


class LoginFlowTest(unittest.TestCase):
    def test_login_sets_cookie_and_verify_returns_role(self):
        c = client()
        r = login(c, next_url="/d/db-overview")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/d/db-overview")
        cookie = r.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        v = c.get("/auth/verify")
        self.assertEqual(v.status_code, 200)
        self.assertEqual(v.headers["x-user"], "admin")
        self.assertEqual(v.headers["x-role"], "Admin")
        self.assertEqual(c.get("/auth/verify", params={"role": "admin"}).status_code, 200)

    def test_verify_without_cookie_is_401(self):
        self.assertEqual(client().get("/auth/verify").status_code, 401)

    def test_logout_revokes_session(self):
        c = client()
        login(c)
        token = c.cookies.get(auth.COOKIE)
        c.get("/auth/logout")
        replay = client()
        replay.cookies.set(auth.COOKIE, token)
        self.assertEqual(replay.get("/auth/verify").status_code, 401)

    def test_forged_token_rejected(self):
        import jwt
        forged = jwt.encode({"sid": "x", "sub": "admin", "role": "admin", "exp": int(time.time()) + 60},
                            "wrong-secret", algorithm="HS256")
        c = client()
        c.cookies.set(auth.COOKIE, forged)
        self.assertEqual(c.get("/auth/verify").status_code, 401)

    def test_start_login_encodes_original_uri(self):
        r = client().get("/auth/start-login", headers={"x-original-uri": "/d/x?from=now-1h&to=now"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/auth/login?next=%2Fd%2Fx%3Ffrom%3Dnow-1h%26to%3Dnow")
        r = client().get("/auth/start-login", headers={"x-original-uri": "//evil.example"})
        self.assertEqual(r.headers["location"], "/auth/login?next=%2F")


class LockoutTest(unittest.TestCase):
    def test_lockout_is_per_ip(self):
        attacker = client("10.9.9.9")
        codes = [login(attacker, "lock_user", "bad").status_code for _ in range(6)]
        self.assertEqual(codes, [401] * 5 + [429])
        # інша адреса з правильним паролем не заблокована (admin не можна заблокувати ззовні)
        for _ in range(6):
            login(attacker, "admin", "bad")
        self.assertEqual(login(client("10.0.0.2")).status_code, 303)


class UsersAdminTest(unittest.TestCase):
    def setUp(self):
        self.admin = client("10.0.0.3")
        login(self.admin)

    def test_create_requires_same_origin(self):
        r = self.admin.post("/auth/users", data={"username": "csrf_user", "password": "password123", "role": "viewer"})
        self.assertEqual(r.status_code, 403)
        r = self.admin.post("/auth/users", data={"username": "csrf_user", "password": "password123", "role": "viewer"},
                            headers={"origin": "http://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_create_validates_username_and_role(self):
        for name, role in (("bad/name", "viewer"), ("x" * 65, "viewer"), ("ok_name", "superuser"),
                           ("<script>", "viewer")):
            self.admin.post("/auth/users", data={"username": name, "password": "password123", "role": role},
                            headers=ORIGIN)
            with auth.db() as c:
                self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username = ?", (name,)).fetchone(), name)
        r = self.admin.post("/auth/users", data={"username": "short_pw", "password": "123", "role": "viewer"},
                            headers=ORIGIN)
        with auth.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username = 'short_pw'").fetchone())

    def test_viewer_cannot_manage_users(self):
        r = self.admin.post("/auth/users", data={"username": "viewer1", "password": "password123", "role": "viewer"},
                            headers=ORIGIN)
        self.assertEqual(r.status_code, 303)
        viewer = client("10.0.0.4")
        login(viewer, "viewer1", "password123")
        self.assertEqual(viewer.get("/auth/verify", params={"role": "admin"}).status_code, 403)
        r = viewer.post("/auth/users", data={"username": "evil", "password": "password123", "role": "admin"},
                        headers=ORIGIN)
        self.assertIn("Доступ заборонено", r.text)
        # видалення: сесії viewer відкликаються
        self.admin.post("/auth/users/viewer1/delete", headers=ORIGIN)
        self.assertEqual(viewer.get("/auth/verify").status_code, 401)


if __name__ == "__main__":
    unittest.main()
