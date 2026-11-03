using System.Diagnostics;
using Prometheus;

namespace TelemetrySystem.Api.Observability;

/// <summary>
/// Власні бізнес-метрики API, які збирає Prometheus з ендпоінту /metrics.
/// Стандартні HTTP-метрики (http_requests_received_total, http_request_duration_seconds)
/// додає middleware prometheus-net (UseHttpMetrics).
/// </summary>
public static class AppMetrics
{
    public const string ServiceName = "telemetry-api";

    /// <summary>ActivitySource для власних спанів (видно у Grafana Tempo).</summary>
    public static readonly ActivitySource Tracer = new("TelemetrySystem.Api");

    /// <summary>Типи подій, які шле tracker.js. Решта рахується як "other", інакше будь-хто через
    /// публічний /api/telemetry/track міг би створити необмежену кількість часових рядів у Prometheus.</summary>
    private static readonly HashSet<string> KnownEventTypes = new() { "page_view", "click" };

    public static string EventTypeLabel(string? eventType) =>
        eventType is not null && KnownEventTypes.Contains(eventType) ? eventType : "other";

    public static readonly Counter EventsReceived = Metrics.CreateCounter(
        "telemetry_events_received_total",
        "Кількість подій, прийнятих ендпоінтом /api/telemetry/track",
        new CounterConfiguration { LabelNames = new[] { "event_type" } });

    public static readonly Counter EventsWritten = Metrics.CreateCounter(
        "telemetry_events_written_total",
        "Кількість подій, успішно записаних у PostgreSQL");

    public static readonly Counter EventsWriteErrors = Metrics.CreateCounter(
        "telemetry_events_write_errors_total",
        "Кількість помилок запису подій у PostgreSQL");

    public static readonly Counter EventsDropped = Metrics.CreateCounter(
        "telemetry_events_dropped_total",
        "Події, витіснені з переповненої внутрішньої черги (Channel, DropOldest) і не записані в БД");

    public static readonly Histogram DbWriteDuration = Metrics.CreateHistogram(
        "telemetry_db_write_duration_seconds",
        "Тривалість успішного INSERT однієї події в БД",
        new HistogramConfiguration { Buckets = Histogram.ExponentialBuckets(0.001, 2, 12) });

    public static readonly Gauge ChannelBacklog = Metrics.CreateGauge(
        "telemetry_channel_backlog",
        "Кількість подій у внутрішній черзі (Channel), що чекають запису в БД");

    public static readonly Counter Logins = Metrics.CreateCounter(
        "telemetry_api_logins_total",
        "Спроби входу компаній в API",
        new CounterConfiguration { LabelNames = new[] { "result" } });
}
