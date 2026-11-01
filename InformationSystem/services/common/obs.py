"""Спільні налаштування спостережуваності для Python-сервісів.

* логи   -> JSON у stdout (їх забирає Grafana Alloy і пересилає в Loki);
           у кожному рядку є trace_id, тож з логу можна перейти до трейсу в Tempo;
* трейси -> OpenTelemetry SDK -> OTLP/HTTP -> Grafana Tempo;
* метрики -> prometheus_client (кожен сервіс сам піднімає /metrics).
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        span_ctx = trace.get_current_span().get_span_context()
        if span_ctx.is_valid:
            payload["trace_id"] = format(span_ctx.trace_id, "032x")
            payload["span_id"] = format(span_ctx.span_id, "016x")
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    # бібліотеки занадто балакучі на INFO
    for noisy in ("pika", "urllib3", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(service)


def setup_tracing(service: str) -> trace.Tracer:
    provider = TracerProvider(resource=Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", service),
        "deployment.environment": os.getenv("ENVIRONMENT", "docker"),
    }))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        # імпорт тут, щоб сервіс працював і без колектора (локальний запуск)
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service)


def log_extra(**fields) -> dict:
    """Додаткові поля для JSON-логу: log.info("...", extra=log_extra(user="x"))."""
    return {"extra_fields": fields}
