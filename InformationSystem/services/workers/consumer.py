"""Consumer: читає події з RabbitMQ і пересилає їх у TelemetrySystem.Api (POST /api/telemetry/track),
який записує їх у PostgreSQL.

Контекст трейсу береться із заголовків повідомлення, тому в Tempo видно один наскрізний трейс:
traffic-generator -> RabbitMQ -> ingest-worker -> telemetry-api -> PostgreSQL.
"""
import json
import os
import time

import pika
import requests
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import Counter, Histogram, start_http_server

from common.obs import exit_on_sigterm, log_extra, setup_logging, setup_tracing

SERVICE = "ingest-worker"
log = setup_logging(SERVICE)
tracer = setup_tracing(SERVICE)
RequestsInstrumentor().instrument()
exit_on_sigterm()

API_URL = os.getenv("API_URL", "http://telemetry-api:8080")
RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
QUEUE = os.getenv("EVENTS_QUEUE", "telemetry.events")
DLQ = QUEUE + ".dead"
MAX_RETRIES = 3

PROCESSED = Counter("consumer_messages_processed_total", "Оброблені повідомлення", ["result"])
LATENCY = Histogram("consumer_processing_seconds", "Час обробки одного повідомлення (включно з API)",
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
END_TO_END = Histogram("consumer_end_to_end_seconds", "Затримка від публікації до запису через API",
                       buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30))

session = requests.Session()


def publish_to(ch, queue: str, body: bytes, headers: dict):
    """Публікація зі збереженням заголовків (traceparent, x-retries, x-error) — щоб у DLQ було видно причину."""
    ch.basic_publish("", queue, body, pika.BasicProperties(
        delivery_mode=2, content_type="application/json", headers=headers))


def dead_letter(ch, body: bytes, headers: dict, reason: str):
    publish_to(ch, DLQ, body, {**headers, "x-error": reason[:500]})


def handle(ch, method, props, body):
    headers = dict(props.headers or {})
    ctx = propagate.extract(headers)
    with tracer.start_as_current_span("rabbitmq.consume", context=ctx, kind=SpanKind.CONSUMER) as span,             LATENCY.time():
        span.set_attribute("messaging.system", "rabbitmq")
        span.set_attribute("messaging.destination.name", QUEUE)
        try:
            event = json.loads(body)
            if not isinstance(event, dict):
                raise ValueError("message is not a JSON object")
            span.set_attribute("telemetry.event_type", str(event.get("eventType", "")))
            resp = session.post(f"{API_URL}/api/telemetry/track", timeout=5,
                                headers={"User-Agent": str(event.pop("userAgent", "ingest-worker"))},
                                json=event)
            if 400 <= resp.status_code < 500:
                # API відхилив саму подію — повтори нічого не змінять
                PROCESSED.labels("rejected").inc()
                span.set_status(Status(StatusCode.ERROR, f"HTTP {resp.status_code}"))
                log.error(f"API rejected event with HTTP {resp.status_code}, moved to DLQ")
                dead_letter(ch, body, headers, f"HTTP {resp.status_code}: {resp.text[:200]}")
                ch.basic_ack(method.delivery_tag)
                return
            resp.raise_for_status()
            try:
                END_TO_END.observe(max(0.0, time.time() - float(headers["x-sent-at"])))
            except (KeyError, TypeError, ValueError):
                pass  # без коректного часу відправки затримку просто не рахуємо
            PROCESSED.labels("ok").inc()
            ch.basic_ack(method.delivery_tag)
        except requests.RequestException as e:
            # API недоступний або 5xx — повертаємо в чергу, після MAX_RETRIES — у DLQ
            retries = int(headers.get("x-retries", 0))
            span.set_status(Status(StatusCode.ERROR, str(e)))
            if retries < MAX_RETRIES:
                PROCESSED.labels("retry").inc()
                log.warning(f"API error, retry {retries + 1}/{MAX_RETRIES}: {e!r}")
                publish_to(ch, QUEUE, body, {**headers, "x-retries": retries + 1})
            else:
                PROCESSED.labels("dead").inc()
                log.error(f"Message moved to DLQ after {MAX_RETRIES} retries: {e!r}")
                dead_letter(ch, body, headers, repr(e))
            ch.basic_ack(method.delivery_tag)
            time.sleep(1)
        except (ValueError, TypeError) as e:
            # битий JSON або не об'єкт — немає сенсу повторювати
            PROCESSED.labels("invalid").inc()
            span.set_status(Status(StatusCode.ERROR, str(e)))
            log.error(f"Invalid message dropped to DLQ: {e!r}")
            dead_letter(ch, body, headers, repr(e))
            ch.basic_ack(method.delivery_tag)
        except pika.exceptions.AMQPError:
            raise  # проблеми з'єднання обробляє main(): перепідключення, повідомлення повернеться в чергу
        except Exception as e:
            # будь-яка інша помилка не повинна зупиняти consumer і зациклювати повідомлення
            PROCESSED.labels("invalid").inc()
            span.set_status(Status(StatusCode.ERROR, repr(e)))
            log.exception("Unexpected error, message moved to DLQ")
            dead_letter(ch, body, headers, repr(e))
            ch.basic_ack(method.delivery_tag)



def wait_for_api():
    """Не забираємо повідомлення з черги, доки API не готовий (інакше вони підуть у DLQ)."""
    while True:
        try:
            if session.get(f"{API_URL}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        log.info("Waiting for telemetry-api ...")
        time.sleep(3)


def main():
    start_http_server(int(os.getenv("METRICS_PORT", "8000")))
    wait_for_api()
    while True:
        try:
            conn = pika.BlockingConnection(pika.URLParameters(RABBIT_URL))
            ch = conn.channel()
            ch.queue_declare(queue=QUEUE, durable=True)
            ch.queue_declare(queue=DLQ, durable=True)
            ch.basic_qos(prefetch_count=int(os.getenv("PREFETCH", "50")))
            ch.basic_consume(QUEUE, handle)
            log.info("Consuming", extra=log_extra(queue=QUEUE))
            ch.start_consuming()
        except pika.exceptions.AMQPError as e:
            log.warning(f"RabbitMQ connection problem: {e!r}; reconnecting in 3s")
            time.sleep(3)


if __name__ == "__main__":
    main()
