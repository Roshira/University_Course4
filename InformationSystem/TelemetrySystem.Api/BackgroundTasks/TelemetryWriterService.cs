using System.Diagnostics;
using System.Threading.Channels;
using Microsoft.EntityFrameworkCore;
using TelemetrySystem.Api.Data;
using TelemetrySystem.Api.Models;
using TelemetrySystem.Api.Observability;

namespace TelemetrySystem.Api.BackgroundTasks;

public class TelemetryWriterService : BackgroundService
{
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

        await foreach (var eventData in _channel.Reader.ReadAllAsync(stoppingToken))
        {
            AppMetrics.ChannelBacklog.Set(_channel.Reader.Count);

            // Окремий спан на кожен запис у БД — у Tempo видно SQL-запити Npgsql всередині.
            using var activity = AppMetrics.Tracer.StartActivity("telemetry.write", ActivityKind.Internal);
            activity?.SetTag("telemetry.event_type", eventData.EventType);
            activity?.SetTag("telemetry.app_id", eventData.AppId.ToString());

            var sw = Stopwatch.StartNew();
            try
            {
                using var scope = _serviceProvider.CreateScope();
                var dbContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();

                dbContext.Events.Add(eventData);
                await dbContext.SaveChangesAsync(stoppingToken);

                AppMetrics.EventsWritten.Inc();
                _logger.LogDebug("Event {EventType} for app {AppId} saved", eventData.EventType, eventData.AppId);
            }
            catch (Exception ex)
            {
                AppMetrics.EventsWriteErrors.Inc();
                activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
                _logger.LogError(ex, "Error occurred while saving telemetry data.");
            }
            finally
            {
                AppMetrics.DbWriteDuration.Observe(sw.Elapsed.TotalSeconds);
            }
        }
    }
}
