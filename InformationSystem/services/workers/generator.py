"""Генератор навантаження: імітує відвідувачів сайту, підключеного до AnalyticsSystem.

1. Реєструє демо-компанію в TelemetrySystem.Api і отримує її AppId (+ JWT).
2. Створює воронку (Головна -> Каталог -> Кошик -> Оформлення).
3. Безперервно генерує сесії користувачів (page_view / click) і публікує події
   в RabbitMQ (черга telemetry.events). Далі їх забирає consumer.py і пише в БД через API.
4. Час від часу робить "аналітичні" GET-запити до API (читання з БД).

Інтенсивність змінюється синусоїдою + випадкові "сплески", щоб графіки в Grafana були живими.
"""
import json
import math
import os
import random
import threading
import time
import uuid

import pika
import requests
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from prometheus_client import Counter, Gauge, start_http_server

from common.obs import log_extra, setup_logging, setup_tracing

SERVICE = "traffic-generator"
log = setup_logging(SERVICE)
tracer = setup_tracing(SERVICE)
RequestsInstrumentor().instrument()

API_URL = os.getenv("API_URL", "http://telemetry-api:8080")
RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
QUEUE = os.getenv("EVENTS_QUEUE", "telemetry.events")
BASE_RATE = float(os.getenv("BASE_SESSIONS_PER_SEC", "3"))
COMPANY_EMAIL = os.getenv("DEMO_COMPANY_EMAIL", "demo-shop@example.com")
COMPANY_PASSWORD = os.getenv("DEMO_COMPANY_PASSWORD", "demo-password")

EVENTS_PUBLISHED = Counter("generator_events_published_total", "Опубліковані в RabbitMQ події", ["event_type"])
SESSIONS = Counter("generator_sessions_total", "Згенеровані сесії відвідувачів", ["device"])
PUBLISH_ERRORS = Counter("generator_publish_errors_total", "Помилки публікації в RabbitMQ")
API_READS = Counter("generator_api_reads_total", "Аналітичні GET-запити до API", ["endpoint", "status"])
CURRENT_RATE = Gauge("generator_target_sessions_per_second", "Поточна цільова інтенсивність сесій")

# Сторінки демо-магазину та кнопки на них (українські назви, як очікує tracker.js)
SITE = {
    "/": ["Каталог", "Акції", "Увійти", "Підписатися на розсилку"],
    "/catalog": ["Додати в кошик", "Фільтр за ціною", "Наступна сторінка", "Детальніше"],
    "/product": ["Додати в кошик", "Відгуки", "Поділитися"],
    "/cart": ["Оформити замовлення", "Видалити товар", "Продовжити покупки"],
    "/checkout": ["Підтвердити оплату", "Поле: Email", "Поле: Телефон"],
    "/sale": ["Каталог", "Додати в кошик"],
}
FUNNEL = ["Каталог", "Додати в кошик", "Оформити замовлення", "Підтвердити оплату"]
USER_AGENTS = {
    "desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1",
    "tablet": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) Safari/604.1",
}


# ---------------------------------------------------------------- API setup
def wait_for_api():
    while True:
        try:
            if requests.get(f"{API_URL}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        log.info("Waiting for telemetry-api ...")
        time.sleep(3)


def ensure_company() -> tuple[str, str]:
    """Повертає (app_id, jwt) демо-компанії; реєструє її за потреби."""
    with tracer.start_as_current_span("setup.ensure_company"):
        requests.post(f"{API_URL}/api/auth/register", timeout=10, json={
            "name": "Demo Shop", "email": COMPANY_EMAIL, "password": COMPANY_PASSWORD})
        r = requests.post(f"{API_URL}/api/auth/login", timeout=10, json={
            "email": COMPANY_EMAIL, "password": COMPANY_PASSWORD})
        r.raise_for_status()
        data = r.json()
        token = data.get("token") or data.get("Token")
        app_id = data.get("appId") or data.get("AppId")
        headers = {"Authorization": f"Bearer {token}"}
        existing = requests.get(f"{API_URL}/api/telemetry/custom-funnels", headers=headers, timeout=10)
        if existing.ok and not existing.json():
            requests.post(f"{API_URL}/api/telemetry/funnels", headers=headers, timeout=10,
                          json={"name": "Покупка", "steps": FUNNEL})
            log.info("Demo funnel created")
        log.info("Demo company ready", extra=log_extra(app_id=app_id))
        return app_id, token


# ---------------------------------------------------------------- RabbitMQ
class Publisher:
    def __init__(self):
        self.conn = None
        self.ch = None

    def connect(self):
        while True:
            try:
                self.conn = pika.BlockingConnection(pika.URLParameters(RABBIT_URL))
                self.ch = self.conn.channel()
                self.ch.queue_declare(queue=QUEUE, durable=True)
                log.info("Connected to RabbitMQ", extra=log_extra(queue=QUEUE))
                return
            except pika.exceptions.AMQPError as e:
                log.warning(f"RabbitMQ not ready: {e}")
                time.sleep(3)

    def publish(self, event: dict):
        headers: dict = {}
        propagate.inject(headers)  # traceparent -> заголовки AMQP, consumer продовжить трейс
        headers["x-sent-at"] = str(time.time())
        try:
            self.ch.basic_publish(
                exchange="", routing_key=QUEUE, body=json.dumps(event, ensure_ascii=False).encode(),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2,
                                                headers=headers))
            EVENTS_PUBLISHED.labels(event["eventType"]).inc()
        except pika.exceptions.AMQPError:
            PUBLISH_ERRORS.inc()
            log.exception("Publish failed, reconnecting")
            self.connect()


# ---------------------------------------------------------------- simulation
def simulate_session(pub: Publisher, app_id: str):
    device = random.choices(list(USER_AGENTS), weights=[55, 38, 7])[0]
    session_id = str(uuid.uuid4())
    SESSIONS.labels(device).inc()
    with tracer.start_as_current_span("generator.session") as span:
        span.set_attribute("session.id", session_id)
        span.set_attribute("session.device", device)
        page = "/"
        steps = random.randint(1, 8)
        funnel_progress = 0
        for _ in range(steps):
            base = {"appId": app_id, "sessionId": session_id, "url": page, "userAgent": USER_AGENTS[device]}
            pub.publish({**base, "eventType": "page_view", "elementTag": "Перегляд сторінки"})
            # з певною ймовірністю користувач рухається по воронці
            if funnel_progress < len(FUNNEL) and random.random() < 0.55 - funnel_progress * 0.1:
                button = FUNNEL[funnel_progress]
                funnel_progress += 1
            else:
                button = random.choice(SITE[page])
            pub.publish({**base, "eventType": "click", "elementTag": button})
            page = {"Каталог": "/catalog", "Додати в кошик": "/cart", "Оформити замовлення": "/checkout",
                    "Акції": "/sale", "Детальніше": "/product"}.get(button, random.choice(list(SITE)))
            if random.random() < 0.15:  # пішов з сайту
                break
        span.set_attribute("session.funnel_progress", funnel_progress)


def analyst_loop(token: str):
    """Імітує аналітика, що відкриває дашборд AnalyticsSystem (SELECT-навантаження на БД)."""
    endpoints = ["stats", "clicks", "daily", "url-stats", "custom-funnels"]
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        ep = random.choice(endpoints)
        with tracer.start_as_current_span(f"analyst.get_{ep}"):
            try:
                r = requests.get(f"{API_URL}/api/telemetry/{ep}", headers=headers, timeout=15)
                API_READS.labels(ep, str(r.status_code)).inc()
                if r.status_code == 401:
                    _, new_token = ensure_company()
                    headers["Authorization"] = f"Bearer {new_token}"
            except requests.RequestException as e:
                API_READS.labels(ep, "error").inc()
                log.warning(f"Analyst request failed: {e}")
        time.sleep(random.uniform(2, 6))


def current_rate(t0: float) -> float:
    minutes = (time.time() - t0) / 60
    wave = 1 + 0.6 * math.sin(minutes / 5 * 2 * math.pi)       # хвиля з періодом 5 хв
    burst = 3 if random.random() < 0.01 else 1                  # рідкісні сплески
    return max(0.2, BASE_RATE * wave * burst)


def main():
    start_http_server(int(os.getenv("METRICS_PORT", "8000")))
    wait_for_api()
    app_id, token = ensure_company()
    threading.Thread(target=analyst_loop, args=(token,), daemon=True).start()

    pub = Publisher()
    pub.connect()
    t0 = time.time()
    while True:
        rate = current_rate(t0)
        CURRENT_RATE.set(rate)
        simulate_session(pub, app_id)
        pub.conn.sleep(random.expovariate(rate))  # sleep, що обробляє heartbeat RabbitMQ


if __name__ == "__main__":
    main()
