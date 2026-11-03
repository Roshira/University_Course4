using System.Diagnostics;
using System.Threading.Channels;
using Microsoft.EntityFrameworkCore;
using TelemetrySystem.Api.Data;
using TelemetrySystem.Api.Models;
using TelemetrySystem.Api.Observability;

namespace TelemetrySystem.Api.BackgroundTasks;

public class TelemetryWriterService : BackgroundService
{
    // скільки часу при зупинці дописувати в БД події, що залишились у черзі
    private static readonly TimeSpan DrainTimeout = TimeSpan.FromSeconds(5);

    private readonly Channel<EventData> _channel;
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<TelemetryWriterService> _logger;

    public TelemetryWriterService(
        Channel<EventData> channel,
        IServiceProvider serviceProvider,
        ILogger<TelemetryWriterService> logger)
    {
        _channel = channel;
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Background Telemetry Writer started.");

        try
        {
            await foreach (var eventData in _channel.Reader.ReadAllAsync(stoppingToken))
            {
                await WriteAsync(eventData);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            // звичайна зупинка сервісу — не помилка
        }

        // Події, які вже прийняті API, але ще не записані, не повинні губитися при docker stop.
        var deadline = Stopwatch.StartNew();
        var drained = 0;
        while (deadline.Elapsed < DrainTimeout && _channel.Reader.TryRead(out var rest))
        {
            await WriteAsync(rest);
            drained++;
        }
        _logger.LogInformation("Background Telemetry Writer stopped, {Drained} queued events written on shutdown, {Left} left",
            drained, _channel.Reader.Count);
    }

    private async Task WriteAsync(EventData eventData)
    {
        // Окремий спан на кожен запис у БД — у Tempo видно SQL-запити Npgsql всередині.
        // Батьківський контекст — HTTP-запит, що прийняв подію, тож запис у БД є частиною наскрізного трейсу.
        using var activity = AppMetrics.Tracer.StartActivity(
            "telemetry.write", ActivityKind.Internal, EventTraceContext.Take(eventData));
        activity?.SetTag("telemetry.event_type", eventData.EventType);
        activity?.SetTag("telemetry.app_id", eventData.AppId.ToString());

        var sw = Stopwatch.StartNew();
        try
        {
            using var scope = _serviceProvider.CreateScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();

            dbContext.Events.Add(eventData);
            // без stoppingToken: запис, що вже почався, доводимо до кінця навіть під час зупинки
            await dbContext.SaveChangesAsync(CancellationToken.None);

            AppMetrics.EventsWritten.Inc();
            AppMetrics.DbWriteDuration.Observe(sw.Elapsed.TotalSeconds);
            _logger.LogDebug("Event {EventType} for app {AppId} saved", eventData.EventType, eventData.AppId);
        }
        catch (Exception ex)
        {
            AppMetrics.EventsWriteErrors.Inc();
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            _logger.LogError(ex, "Error occurred while saving telemetry data.");
        }
    }
}
